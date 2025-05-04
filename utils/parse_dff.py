# Renderware DFF FrameList Parser

import struct
import io
import traceback
import sys
import argparse # コマンドライン引数の処理用

# Renderware Chunk IDs
RWCHUNK_STRUCT_ID = 0x01
RWCHUNK_FRAMELIST_ID = 0x0E
RWCHUNK_CLUMP_ID = 0x10

def read_chunk_header(stream):
    """
    Reads a chunk header (ID, Size, Version) from the current stream position.
    Returns:
        tuple: (chunk_id, chunk_size, chunk_version) or (None, None, None) if EOF.
    """
    header_bytes = stream.read(12)
    if len(header_bytes) < 12:
        return None, None, None
    # < = Little-endian, I = Unsigned 4-byte integer
    chunk_id, chunk_size, chunk_version = struct.unpack('<III', header_bytes)
    return chunk_id, chunk_size, chunk_version

def find_chunk_data(stream, target_chunk_id, search_limit):
    """
    Searches for a chunk with the target ID within the stream up to the search limit.
    Args:
        stream (file object): Binary file stream to search within.
        target_chunk_id (int): The ID of the chunk to find.
        search_limit (int): Absolute file position marking the search boundary.
    Returns:
        bytes or None: The data part of the target chunk, or None if not found.
    """
    # Keep track of the starting position in case we need to backtrack on error
    start_search_pos = stream.tell()
    chunk_data = None

    try:
        while stream.tell() < search_limit:
            chunk_start_pos = stream.tell()
            chunk_id, chunk_size, chunk_version = read_chunk_header(stream)

            if chunk_id is None:
                # print("Debug: Failed to read header (EOF?)")
                break # Cannot read header

            chunk_data_start_pos = stream.tell()
            chunk_data_end_pos = chunk_data_start_pos + chunk_size

            # Validate chunk size against the search limit
            if chunk_data_end_pos > search_limit:
                print(f"Warning: Chunk (ID: {chunk_id:#04x} at {chunk_start_pos:#x}) size ({chunk_size}) "
                      f"exceeds search limit ({search_limit:#x}). Possible data corruption.")
                # Go back to the start of this invalid chunk header and stop searching here
                stream.seek(chunk_start_pos)
                return None

            # print(f"Debug: Found Chunk ID={chunk_id:#04x}, Size={chunk_size}, Ver={chunk_version:#08x} at {chunk_start_pos:#x}")

            if chunk_id == target_chunk_id:
                # Target found! Read and return its data payload.
                print(f"Target chunk (ID: {target_chunk_id:#04x}) found at {chunk_start_pos:#x}. Data size: {chunk_size}")
                chunk_data = stream.read(chunk_size)
                if len(chunk_data) < chunk_size:
                     print(f"Warning: Incomplete data read for target chunk (ID: {chunk_id:#04x}). Expected {chunk_size}, got {len(chunk_data)}.")
                     # Return what was read, or None if nothing significant? For now, return None.
                     chunk_data = None
                # Found the target, exit the loop
                break
            else:
                # Not the target, skip this chunk's data payload.
                # print(f"  Skipping {chunk_size} bytes from {chunk_data_start_pos:#x}")
                stream.seek(chunk_data_start_pos + chunk_size)

        # After the loop, return the found data (or None if not found)
        return chunk_data

    except Exception as e:
        print(f"Error during chunk search: {e}")
        traceback.print_exc()
        # Attempt to restore original position on error? Might be complex.
        # For simplicity, just return None.
        return None

def parse_frame_struct_data(frame_struct_data, matrix_interpretation='standard'):
    """
    Parses the data (bytes) from a FrameList's Struct chunk to generate a frame list.
    Args:
        frame_struct_data (bytes): The data payload of the FrameList's Struct chunk.
                                   (First 4 bytes = frame count, followed by frame data).
        matrix_interpretation (str): How to interpret the rotation matrix.
                                     'standard': Standard Renderware (Column vectors R,U,A -> Transposed for display).
                                     'rwanalyze': Interpretation matching RW Analyze tool.
    Returns:
        list: A list of parsed frame information dictionaries.
    """
    frames = []
    data_stream = io.BytesIO(frame_struct_data) # Treat bytes data like a file stream

    # Frame data structure within the Struct chunk
    # < = Little-endian
    # 9f = 9 floats (Rotation Matrix)
    # 3f = 3 floats (Position)
    # i = signed 4-byte integer (Parent Index)
    # I = unsigned 4-byte integer (Unknown Flags/Data)
    frame_format = '<9f 3f i I'
    frame_size = struct.calcsize(frame_format) # Should be 56 bytes

    if frame_size != 56:
        print(f"Error: Expected frame size (56) does not match calculated size: {frame_size}")
        return []

    try:
        # Read frame count (first 4 bytes)
        count_bytes = data_stream.read(4)
        if len(count_bytes) < 4:
            print("Error: Could not read frame count.")
            return []
        frame_count = struct.unpack('<I', count_bytes)[0]
        print(f"Frame count in FrameList Struct: {frame_count}")

        if frame_count == 0:
             print("Info: Frame count is 0.")
             return []

        # Verify expected data size based on frame count
        expected_data_size = 4 + frame_count * frame_size
        actual_data_size = len(frame_struct_data)
        if actual_data_size < expected_data_size:
            print(f"Warning: Struct data size ({actual_data_size}) is smaller than expected based on frame count ({frame_count}). Expected: {expected_data_size}.")
            # Adjust frame count to what can actually be read
            frame_count = (actual_data_size - 4) // frame_size
            print(f"  -> Attempting to read {frame_count} frames.")
            if frame_count <= 0: return []

        # Read and parse each frame's data
        for i in range(frame_count):
            frame_data_bytes = data_stream.read(frame_size)
            if len(frame_data_bytes) < frame_size:
                print(f"Warning: Unexpected end of data while reading frame {i+1}.")
                break # Stop processing if data is incomplete

            # Unpack the 56 bytes according to the format
            unpacked_data = struct.unpack(frame_format, frame_data_bytes)

            # Extract the 9 floats for the matrix
            matrix_flat = unpacked_data[0:9]
            # Extract the 3 floats for position
            position = unpacked_data[9:12]
            # Extract the parent index (0-based, -1 for root)
            parent_index_0based = unpacked_data[12]
            # Extract the unknown integer
            unknown_int = unpacked_data[13]

            # --- Interpret Rotation Matrix based on the chosen method ---
            matrix_rows = []
            if matrix_interpretation == 'rwanalyze':
                # Interpretation matching RW Analyze tool's apparent output for Frame 5
                # Binary order: R.x, R.y, R.z, U.x, U.y, U.z, A.x, A.y, A.z
                # RW Analyze output seems to be: (R.y, U.x, A.x); (R.x, U.y, A.y); (R.z, U.z, A.z)
                # Indices:                  ( 1 ,  3 ,  6 ); ( 0 ,  4 ,  7 ); ( 2 ,  5 ,  8 )
                try:
                    matrix_rows = [
                        (matrix_flat[1], matrix_flat[3], matrix_flat[6]), # Row 0
                        (matrix_flat[0], matrix_flat[4], matrix_flat[7]), # Row 1
                        (matrix_flat[2], matrix_flat[5], matrix_flat[8])  # Row 2
                    ]
                except IndexError:
                     print(f"Error interpreting matrix for 'rwanalyze' on frame {i+1}. Data length: {len(matrix_flat)}")
                     matrix_rows = [(0,0,0),(0,0,0),(0,0,0)] # Provide default on error
            else: # Default 'standard' interpretation
                # Standard Renderware: Assumes column vectors (Right, Up, At) stored sequentially.
                # We transpose it for row-based display matching the user's text format.
                # Binary order: R.x, R.y, R.z, U.x, U.y, U.z, A.x, A.y, A.z
                # Indices:        0    1    2    3    4    5    6    7    8
                # Display rows: (R.x, U.x, A.x); (R.y, U.y, A.y); (R.z, U.z, A.z)
                try:
                    matrix_rows = [
                        (matrix_flat[0], matrix_flat[3], matrix_flat[6]), # Row 0 (M00, M01, M02)
                        (matrix_flat[1], matrix_flat[4], matrix_flat[7]), # Row 1 (M10, M11, M12)
                        (matrix_flat[2], matrix_flat[5], matrix_flat[8])  # Row 2 (M20, M21, M22)
                    ]
                except IndexError:
                     print(f"Error interpreting matrix for 'standard' on frame {i+1}. Data length: {len(matrix_flat)}")
                     matrix_rows = [(0,0,0),(0,0,0),(0,0,0)] # Provide default on error

            # Convert parent index to 1-based string or "none"
            parent_frame_str = "none" if parent_index_0based == -1 else str(parent_index_0based + 1)

            # Store parsed frame information
            frame_info = {
                "id": i + 1,
                "matrix_rows": matrix_rows,
                "position": position,
                "parent": parent_frame_str,
                "unknown_int": unknown_int
            }
            frames.append(frame_info)

    except struct.error as e:
        print(f"Struct Error: Failed to unpack frame data: {e}")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"An unexpected error occurred during frame parsing: {e}")
        traceback.print_exc()
        return []

    return frames

def process_dff_file(dff_file_path, matrix_interpretation='standard'):
    """
    Processes a DFF file to find and parse the FrameList.
    Args:
        dff_file_path (str): Path to the DFF file.
        matrix_interpretation (str): How to interpret the rotation matrix ('standard' or 'rwanalyze').
    Returns:
        list: A list of parsed frame information dictionaries, or an empty list on failure.
    """
    parsed_frames = []
    try:
        with open(dff_file_path, 'rb') as dff_stream:
            print(f"Opened DFF file: {dff_file_path}")

            # Get file size for boundary checks
            dff_stream.seek(0, io.SEEK_END)
            file_size = dff_stream.tell()
            dff_stream.seek(0, io.SEEK_SET)
            print(f"File size: {file_size} bytes")

            # 1. Expect Clump chunk at the beginning
            clump_id, clump_size, clump_version = read_chunk_header(dff_stream)
            if clump_id != RWCHUNK_CLUMP_ID:
                print(f"Error: Expected Clump chunk (ID:{RWCHUNK_CLUMP_ID:#04x}) at the start, but found ID: {clump_id:#04x}")
                return []

            print(f"Found Clump chunk (ID: {clump_id:#04x}, Size: {clump_size}, Version: {clump_version:#08x})")
            clump_data_start_pos = dff_stream.tell()
            # Calculate the absolute end position for the Clump chunk's data
            clump_data_limit = min(clump_data_start_pos + clump_size, file_size)

            # 2. Search for FrameList chunk within the Clump chunk
            framelist_data = find_chunk_data(dff_stream, RWCHUNK_FRAMELIST_ID, clump_data_limit)

            if framelist_data:
                # We found FrameList, now process its data
                framelist_stream = io.BytesIO(framelist_data)
                framelist_limit = len(framelist_data)

                # 3. Search for Struct chunk within the FrameList chunk
                struct_data = find_chunk_data(framelist_stream, RWCHUNK_STRUCT_ID, framelist_limit)

                if struct_data:
                    # 4. Parse the Struct data using the specified interpretation
                    parsed_frames = parse_frame_struct_data(struct_data, matrix_interpretation)
                else:
                    print("Error: Struct chunk (ID: 0x01) not found within FrameList chunk.")
            else:
                print("Error: FrameList chunk (ID: 0x0E) not found within Clump chunk.")

            # Optional: Continue searching for other chunks after FrameList if needed
            # Make sure the stream position is at the end of the Clump chunk
            # dff_stream.seek(clump_data_limit)

    except FileNotFoundError:
        print(f"Error: DFF file not found at '{dff_file_path}'")
    except Exception as e:
        print(f"An error occurred while processing the DFF file: {e}")
        traceback.print_exc()

    return parsed_frames

# --- Main execution block ---
if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Parse FrameList from a Renderware DFF file.')
    parser.add_argument('dff_file', help='Path to the input DFF binary file.')
    parser.add_argument('-i', '--interpretation',
                        choices=['standard', 'rwanalyze'],
                        default='standard',
                        help='Rotation matrix interpretation method: "standard" (default) or "rwanalyze".')

    # Parse arguments
    args = parser.parse_args()

    # Process the DFF file with the specified interpretation
    result_frames = process_dff_file(args.dff_file, args.interpretation)

    # --- Display results ---
    if result_frames:
        print(f"\n--- Parsed FrameList ({len(result_frames)} frames) using '{args.interpretation}' interpretation ---")
        total_frames = len(result_frames)
        for frame in result_frames:
            print("-" * 20)
            print(f"[Frame {frame['id']} of {total_frames}]")
            # Format matrix for printing with 3 decimal places
            matrix_str = ";".join(
                f"({row[0]:.3f}; {row[1]:.3f}; {row[2]:.3f})" for row in frame['matrix_rows']
            )
            print(f"  Rotation Matrix = {matrix_str}")
            # Format position for printing with 3 decimal places
            pos_str = f"({frame['position'][0]:.3f};{frame['position'][1]:.3f};{frame['position'][2]:.3f})"
            print(f"  Position = {pos_str}")
            print(f"  Parent Frame = {frame['parent']}")
            print(f"  Integer = {frame['unknown_int']}") # Display the unknown integer
    else:
        print("\nFailed to parse frame data or FrameList not found.")