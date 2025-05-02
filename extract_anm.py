import os
import glob

# --- Configuration ---
# Folder containing the .ame files to process
input_folder = "output/ame"
# Folder where extracted .anm files will be saved
output_folder = "output/anm"
# Header bytes to search for (RenderWare ANM)
anm_header = b'\x1B\x00\x00\x00'
# --- End Configuration ---

def extract_anm_files(input_filename, output_dir, header_bytes):
    """
    Finds and extracts data blocks starting with header_bytes from a single binary file.

    Args:
        input_filename (str): Path to the input binary file (.ame).
        output_dir (str): Directory to save the extracted .anm files.
        header_bytes (bytes): The byte sequence marking the start of a block.

    Returns:
        int: The number of files extracted from this input file.
    """
    print(f"\nProcessing file: {input_filename}")
    if not os.path.exists(input_filename):
        print(f"  Error: Input file not found.")
        return 0

    # Get the base name of the input file (without extension) for output naming
    base_name = os.path.splitext(os.path.basename(input_filename))[0]

    try:
        with open(input_filename, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f"  Error reading file: {e}")
        return 0

    header_len = len(header_bytes)
    start_indices = []
    current_pos = 0

    # Find all occurrences of the header
    while True:
        index = data.find(header_bytes, current_pos)
        if index == -1:
            break
        start_indices.append(index)
        current_pos = index + 1 # Start next search 1 byte after found header

    if not start_indices:
        print(f"  No ANM header ({header_bytes.hex()}) found.")
        return 0

    print(f"  Found {len(start_indices)} potential ANM block(s). Extracting...")

    extracted_count = 0
    for i, start_index in enumerate(start_indices):
        # Determine the end index for the current block
        if i + 1 < len(start_indices):
            end_index = start_indices[i+1]
        else:
            # Last block goes to the end of the file
            end_index = len(data)

        # Extract the data chunk (including the header)
        anm_data = data[start_index:end_index]

        # Construct the output filename
        output_filename = os.path.join(output_dir, f"{base_name}_{extracted_count}.anm")

        # Write the extracted data to a new file
        try:
            with open(output_filename, 'wb') as out_f:
                out_f.write(anm_data)
            print(f"  Successfully extracted: {output_filename} ({len(anm_data)} bytes)")
            extracted_count += 1
        except Exception as e:
            print(f"  Error writing file {output_filename}: {e}")

    return extracted_count

# --- Main execution ---
if __name__ == "__main__":
    print("Starting batch ANM extraction...")
    print(f"Input folder: {input_folder}")
    print(f"Output folder: {output_folder}")

    # Create output directory if it doesn't exist
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            print(f"Created output folder: {output_folder}")
        except Exception as e:
            print(f"Error: Could not create output folder {output_folder}: {e}")
            exit() # Exit if output folder cannot be created

    # Find all .ame files in the input folder
    search_pattern = os.path.join(input_folder, "*.ame")
    ame_files = glob.glob(search_pattern)

    if not ame_files:
        print(f"No .ame files found in {input_folder}")
        exit()

    print(f"Found {len(ame_files)} .ame file(s) to process.")

    total_extracted = 0
    total_processed = 0

    # Process each .ame file
    for ame_file_path in ame_files:
        count = extract_anm_files(ame_file_path, output_folder, anm_header)
        total_extracted += count
        total_processed += 1

    print(f"\nBatch extraction finished.")
    print(f"Processed {total_processed} .ame file(s).")
    print(f"Total ANM files extracted: {total_extracted}")