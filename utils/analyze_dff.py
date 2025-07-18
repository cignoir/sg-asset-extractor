import struct
import sys
import os
import io # HAnim PLG スキャン用に io.BytesIO を使用
import argparse # argparse をインポート
import glob # glob をインポートしてワイルドカードを展開

# RenderWareチャンクIDと名前のマッピング
CHUNK_NAMES = {
    0x01: "Struct",
    0x02: "String",
    0x03: "Extension",
    0x05: "Texture",
    0x06: "Material",
    0x07: "Material List",
    0x08: "Frame List Struct / Material List Struct",
    0x0E: "Frame List",
    0x0F: "Geometry",
    0x10: "Clump",
    0x14: "Atomic",
    0x15: "Texture Native",
    0x16: "Texture Dictionary",
    0x1A: "Geometry List",
    0x1C: "Light",
    0x1E: "Frame",
    0x20: "Camera",
    0x116: "Skin PLG",
    0x11E: "HAnim PLG",
    0x133: "UserData PLG",
    0x50E: "Bin Mesh PLG",
}

# HAnim ボーンタイプのマッピング
HANIM_BONE_TYPES = {
    0: "Deformable",
    1: "Nub Bone",
    2: "Unknown",
    3: "Rigid",
}

def get_chunk_name(chunk_id, parent_chunk_id=None):
    """Chunk IDに対応する名前を取得 (親チャンクの文脈を考慮)"""
    if parent_chunk_id == 0x08:
        if chunk_id == 0x07: return "Material"
    elif parent_chunk_id == 0x07:
         if chunk_id == 0x06: return "Texture"
    elif chunk_id == 0x08:
        if parent_chunk_id == 0x0F: return "Material List"
        else: return "Frame List Struct"
    return CHUNK_NAMES.get(chunk_id, f"Unknown (0x{chunk_id:X})")

# --- Specific Struct/Data Parsers ---
def parse_hanim_plg(f, chunk_size, indent, collect_bone_ids_map=None, tsv_output=False):
    """HAnim PLG (0x11E) チャンクのデータを解析。必要ならbone_id_mapに情報を収集"""
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    data_read = 0
    
    # collect_bone_ids_map が None でない場合（情報収集モード）は、詳細表示を抑制
    if not tsv_output:
        print(f"{indent}  --- HAnim Data ---")

    min_header_size = 12
    if chunk_size >= min_header_size:
        try:
            header_part1_data = f.read(min_header_size)
            data_read += min_header_size
            const_256, bone_id_header, bone_count = struct.unpack('<III', header_part1_data)
            
            if not tsv_output:
                print(f"{indent}  Const 256: {const_256}")
                print(f"{indent}  Bone ID: {bone_id_header}") # HAnim PLG自体のヘッダにあるBone ID
                print(f"{indent}  Bone Count: {bone_count}")

            if bone_count > 0:
                remaining_header_size = 8
                full_header_size = min_header_size + remaining_header_size
                if chunk_size >= full_header_size:
                    header_part2_data = f.read(remaining_header_size)
                    data_read += remaining_header_size
                    unknown1, unknown2 = struct.unpack('<II', header_part2_data)
                    if not tsv_output:
                        print(f"{indent}  Unknown 1: {unknown1}")
                        print(f"{indent}  Unknown 2: {unknown2}")

                    bone_struct_size = 12
                    expected_bone_data_size = bone_count * bone_struct_size
                    if data_read + expected_bone_data_size <= chunk_size:
                        for i in range(bone_count):
                            bone_data = f.read(bone_struct_size)
                            if len(bone_data) < bone_struct_size:
                                 if not tsv_output: print(f"{indent}    Warning: Not enough data for bone {i+1}.")
                                 data_read += len(bone_data)
                                 break
                            data_read += bone_struct_size
                            b_id, b_no, bone_type_val = struct.unpack('<III', bone_data)
                            
                            if collect_bone_ids_map is not None:
                                # Bone No をキーとして Bone ID を格納
                                collect_bone_ids_map[b_no] = b_id
                            else:
                                bone_type_name = HANIM_BONE_TYPES.get(bone_type_val, f"Raw ({bone_type_val})")
                                print(f"{indent}  [ Bone {i+1} ]")
                                print(f"{indent}    Bone ID: {b_id}") # こちらが各フレームに対応するID
                                print(f"{indent}    Bone No.: {b_no}")
                                print(f"{indent}    Type: {bone_type_name} ({bone_type_val})")
                    elif not tsv_output:
                        print(f"{indent}  Warning: Not enough data in chunk for {bone_count} bones.")
                elif not tsv_output:
                     print(f"{indent}  Warning: HAnim chunk size ({chunk_size}) too small for full header.")
        except struct.error as e:
            if not tsv_output: print(f"{indent}  Error unpacking HAnim data: {e}")
        except Exception as e:
            if not tsv_output: print(f"{indent}  Unexpected HAnim parsing error: {e}")
    elif not tsv_output:
        print(f"{indent}  Warning: HAnim chunk size ({chunk_size}) too small for min header.")
    
    f.seek(end_pos)
    if not tsv_output:
        print(f"{indent}  --- End HAnim Data ---")

def parse_string_chunk(f, chunk_size, indent, tsv_output=False):
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    decoded_string = ""
    try:
        if chunk_size > 0:
            string_data = f.read(chunk_size)
            try:
                 cleaned_data = string_data.rstrip(b'\x00')
                 decoded_string = cleaned_data.decode('ascii', errors='replace')
            except Exception:
                 decoded_string = f"[Non-ASCII Data: {len(string_data)} bytes]"
            printable_string = ''.join(char for char in decoded_string if char.isprintable())
            if not tsv_output: # TSV出力時は詳細表示しない
                print(f"{indent}  Value: \"{printable_string}\"")
        else:
            if not tsv_output: # TSV出力時は詳細表示しない
                print(f"{indent}  Value: \"\" (Empty String)")
    except Exception as e:
        if not tsv_output: # TSV出力時は詳細表示しない
            print(f"{indent}  Error reading String data: {e}")
    f.seek(end_pos)

def parse_atomic_struct(f, chunk_size, indent, counts, tsv_output=False):
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    expected_size = 16
    if not tsv_output: print(f"{indent}  --- Atomic Struct Data ---")
    if chunk_size >= expected_size:
        try:
            struct_data = f.read(expected_size)
            frame_index, geo_index, unknown1, unknown2 = struct.unpack('<IIII', struct_data)
            if not tsv_output:
                print(f"{indent}  Frame Index: {frame_index}")
                print(f"{indent}  Geometry Index: {geo_index}")
                print(f"{indent}  Unknown 1: {unknown1}")
                print(f"{indent}  Unknown 2: {unknown2}")
                if chunk_size > expected_size:
                    print(f"{indent}  Warning: Atomic Struct has unexpected extra data ({chunk_size - expected_size} bytes).")
            counts['atomic_count'] += 1 # Atomic Count をインクリメント
        except struct.error as e:
            if not tsv_output: print(f"{indent}  Error unpacking Atomic Struct data: {e}")
        except Exception as e:
            if not tsv_output: print(f"{indent}  Unexpected Atomic Struct parsing error: {e}")
    else:
        if not tsv_output: print(f"{indent}  Warning: Atomic Struct chunk size ({chunk_size}) smaller than expected ({expected_size} bytes).")
    f.seek(end_pos)
    if not tsv_output: print(f"{indent}  --- End Atomic Struct Data ---")

def parse_geometry_list_struct(f, chunk_size, indent, counts, tsv_output=False):
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    expected_size = 4
    if not tsv_output: print(f"{indent}  --- Geometry List Struct Data ---")
    if chunk_size >= expected_size:
        try:
            struct_data = f.read(expected_size)
            geometry_count, = struct.unpack('<I', struct_data)
            if not tsv_output: print(f"{indent}  Geometry Count: {geometry_count}")
            counts['geometry_count'] = geometry_count # Geometry Count を格納
            if chunk_size > expected_size:
                if not tsv_output: print(f"{indent}  Warning: Geometry List Struct has unexpected extra data ({chunk_size - expected_size} bytes).")
        except struct.error as e:
            if not tsv_output: print(f"{indent}  Error unpacking Geometry List Struct data: {e}")
        except Exception as e:
            if not tsv_output: print(f"{indent}  Unexpected Geometry List Struct parsing error: {e}")
    else:
        if not tsv_output: print(f"{indent}  Warning: Geometry List Struct chunk size ({chunk_size}) smaller than expected ({expected_size} bytes).")
    f.seek(end_pos)
    if not tsv_output: print(f"{indent}  --- End Geometry List Struct Data ---")

def parse_material_list_struct(f, chunk_size, indent, counts, tsv_output=False):
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    expected_size = 8
    if not tsv_output: print(f"{indent}  --- Material List Struct Data ---")
    if chunk_size >= expected_size:
        try:
            struct_data = f.read(expected_size)
            material_count, integer1 = struct.unpack('<ii', struct_data)
            if not tsv_output:
                print(f"{indent}  Material Count: {material_count}")
                print(f"{indent}  Integer 1: {integer1}")
                if chunk_size > expected_size:
                    print(f"{indent}  Warning: Material List Struct has unexpected extra data ({chunk_size - expected_size} bytes).")
            counts['material_count'] = material_count # Material Count を格納
        except struct.error as e:
            if not tsv_output: print(f"{indent}  Error unpacking Material List Struct data: {e}")
        except Exception as e:
            if not tsv_output: print(f"{indent}  Unexpected Material List Struct parsing error: {e}")
    else:
        if not tsv_output: print(f"{indent}  Warning: Material List Struct chunk size ({chunk_size}) smaller than expected ({expected_size} bytes).")
    f.seek(end_pos)
    if not tsv_output: print(f"{indent}  --- End Material List Struct Data ---")

def parse_material_struct(f, chunk_size, indent, counts, tsv_output=False):
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    expected_size = 20
    if not tsv_output: print(f"{indent}  --- Material Struct Data ---")
    if chunk_size >= expected_size:
        try:
            struct_data = f.read(expected_size)
            int1, color_rgba, int2, tex_count, unknown_float = struct.unpack('<iIiif', struct_data)
            r, g, b, a = (color_rgba & 0xFF), (color_rgba >> 8 & 0xFF), (color_rgba >> 16 & 0xFF), (color_rgba >> 24 & 0xFF)
            if not tsv_output:
                print(f"{indent}  Integer 1: {int1}")
                print(f"{indent}  Color RGBA: ({r}, {g}, {b}, {a}) (Raw: {color_rgba})")
                print(f"{indent}  Integer 2: {int2}")
                print(f"{indent}  Texture Count: {tex_count}")
                print(f"{indent}  Unknown Float: {unknown_float:.3f}")
                if chunk_size > expected_size:
                    print(f"{indent}  Warning: Material Struct has unexpected extra data ({chunk_size - expected_size} bytes).")
            counts['texture_count'] += tex_count # Texture Count を加算
        except struct.error as e:
            if not tsv_output: print(f"{indent}  Error unpacking Material Struct data: {e}")
        except Exception as e:
            if not tsv_output: print(f"{indent}  Unexpected Material Struct parsing error: {e}")
    else:
        if not tsv_output: print(f"{indent}  Warning: Material Struct chunk size ({chunk_size}) smaller than expected ({expected_size} bytes).")
    f.seek(end_pos)
    if not tsv_output: print(f"{indent}  --- End Material Struct Data ---")

def parse_frame_list_struct(f, chunk_size, indent, counts, bone_id_map=None, tsv_output=False):
    """Frame List (0x0E) 内の Struct (0x01) を解析 (BoneID表示対応)"""
    start_pos = f.tell()
    end_pos = start_pos + chunk_size
    if not tsv_output: print(f"{indent}  --- Frame List Struct Data ---")
    if bone_id_map is None: bone_id_map = {} # 安全のため

    frame_count_bytes = f.read(4)
    if len(frame_count_bytes) < 4:
        if not tsv_output: print(f"{indent}  Error: Could not read frame count.")
        f.seek(end_pos); return
    try:
        frame_count, = struct.unpack('<I', frame_count_bytes)
        if not tsv_output: print(f"{indent}  Frame Count: {frame_count}")
        counts['frame_count'] = frame_count # Frame Count を格納
    except struct.error as e:
        if not tsv_output: print(f"{indent}  Error unpacking frame count: {e}")
        f.seek(end_pos); return

    bytes_per_frame = 56
    expected_total_data_size = 4 + frame_count * bytes_per_frame
    if chunk_size < expected_total_data_size:
        if not tsv_output: print(f"{indent}  Warning: Frame List Struct chunk size ({chunk_size}) smaller than expected ({expected_total_data_size} bytes) for {frame_count} frames.")
        f.seek(end_pos); return

    for i in range(frame_count):
        frame_data_start_pos = f.tell()
        if frame_data_start_pos + bytes_per_frame > end_pos:
            if not tsv_output: print(f"{indent}    Warning: Not enough data remaining for frame {i+1}.")
            break
        try:
            frame_data = f.read(bytes_per_frame)
            values = struct.unpack('<fffffffff fff i i', frame_data)
            matrix, position, parent_index, last_int = values[0:9], values[9:12], values[12], values[13]
            
            # フレームインデックス i (Bone No. に対応) を使って BoneID を取得
            # Get BoneID using frame index i (corresponds to Bone No.)
            current_bone_id = bone_id_map.get(i, "N/A") # 見つからない場合は "N/A"

            if not tsv_output:
                print(f"{indent}  [ Frame {i+1} of {frame_count} (BoneID: {current_bone_id}) ]")
                print(f"{indent}    Rotation Matrix: ({matrix[0]:.3f}; {matrix[1]:.3f}; {matrix[2]:.3f}; ...)")
                print(f"{indent}    Position: ({position[0]:.3f}; {position[1]:.3f}; {position[2]:.3f})")
                parent_display = "none" if parent_index == -1 else str(parent_index + 1)
                print(f"{indent}    Parent Frame: {parent_display}")
                print(f"{indent}    Integer: {last_int}")
        except struct.error as e:
            if not tsv_output: print(f"{indent}    Error unpacking data for frame {i+1}: {e}")
            f.seek(end_pos); return
        except Exception as e:
            if not tsv_output: print(f"{indent}    An unexpected error occurred during frame {i+1} parsing: {e}")
            f.seek(end_pos); return
    if f.tell() != end_pos: f.seek(end_pos)
    if not tsv_output: print(f"{indent}  --- End Frame List Struct Data ---")

# --- Main Parsing Logic ---
def parse_chunk(f, end_offset, indent="", parent_id=None, bone_id_map_for_frame_struct=None, counts=None, tsv_output=False):
    """指定されたファイルオフセットからチャンクを再帰的に解析"""
    CONTAINER_CHUNK_IDS = {
        0x03, 0x0E, 0x10, 0x16, 0x1A, 0x0F, 0x08, 0x07, 0x06, 0x05, 0x14,
    }

    while f.tell() < end_offset:
        current_pos = f.tell()
        if current_pos >= end_offset: break

        header_data = f.read(12)
        if len(header_data) < 12:
            if end_offset - current_pos >= 12 and not tsv_output:
                 print(f"{indent}Warning: Unexpected end of data at 0x{current_pos:X}.")
            break

        try:
            chunk_id, chunk_size, lib_id_ver = struct.unpack('<III', header_data)
        except struct.error:
            if not tsv_output: print(f"{indent}Error: Could not unpack header at 0x{current_pos:X}")
            f.seek(end_offset)
            break

        chunk_name = get_chunk_name(chunk_id, parent_id)
        chunk_data_start = f.tell()
        chunk_data_end = chunk_data_start + chunk_size

        if chunk_size > (end_offset - current_pos + 12) or chunk_data_end > end_offset:
             if not tsv_output: print(f"{indent}Error: Chunk '{chunk_name}' (0x{chunk_id:X} at 0x{current_pos:X}) size {chunk_size} invalid/exceeds parent boundary 0x{end_offset:X}.")
             f.seek(end_offset)
             break

        is_container = chunk_id in CONTAINER_CHUNK_IDS and chunk_size > 0
        prefix = "+ " if (is_container and chunk_id not in [0x08, 0x01]) or \
                         (chunk_id == 0x01 and parent_id in [0x14, 0x1A, 0x08, 0x07, 0x0E]) else "  "
        if not tsv_output: print(f"{indent}{prefix}{chunk_name} ( {chunk_size} bytes @ 0x{current_pos:X} ) - [ 0x{chunk_id:X} ]")

        # --- Specific Chunk Parsing & Recursion ---
        if chunk_id == 0x0E: # Frame List - 特別処理でHAnim情報を先に収集
            collected_bone_ids = {}
            # FrameListチャンクのデータを一時的に読み込んでHAnim情報をスキャン
            framelist_content_start_abs = f.tell() # 現在の絶対位置
            framelist_data_bytes = f.read(chunk_size) # チャンクデータを読み込む
            f.seek(framelist_content_start_abs) # ポインタを戻す

            with io.BytesIO(framelist_data_bytes) as framelist_stream:
                temp_scan_pos = 0
                while temp_scan_pos < chunk_size:
                    framelist_stream.seek(temp_scan_pos)
                    child_header_data = framelist_stream.read(12)
                    if len(child_header_data) < 12: break
                    
                    child_id_fl, child_size_fl, _ = struct.unpack('<III', child_header_data)
                    child_data_start_fl = temp_scan_pos + 12

                    if child_id_fl == 0x03: # Extension
                        ext_content_start_fl = child_data_start_fl
                        ext_content_end_fl = ext_content_start_fl + child_size_fl
                        temp_ext_scan_pos_fl = 0 # Extensionデータ内の相対オフセット
                        
                        # Extensionデータをサブストリームとして扱う
                        framelist_stream.seek(ext_content_start_fl)
                        extension_data_bytes = framelist_stream.read(child_size_fl)
                        with io.BytesIO(extension_data_bytes) as extension_stream:
                            while temp_ext_scan_pos_fl < child_size_fl:
                                extension_stream.seek(temp_ext_scan_pos_fl)
                                hanim_header_data = extension_stream.read(12)
                                if len(hanim_header_data) < 12: break
                                
                                hanim_id, hanim_s, _ = struct.unpack('<III', hanim_header_data)
                                hanim_data_start_ext = temp_ext_scan_pos_fl + 12

                                if hanim_id == 0x11E:
                                    extension_stream.seek(hanim_data_start_ext)
                                    # parse_hanim_plgを情報収集モードで呼び出す
                                    parse_hanim_plg(extension_stream, hanim_s, indent + "    ", collect_bone_ids_map=collected_bone_ids, tsv_output=tsv_output)
                                    if collected_bone_ids: # 主要なHAnim情報が見つかれば十分
                                        break 
                                temp_ext_scan_pos_fl = hanim_data_start_ext + hanim_s
                        if collected_bone_ids: break # Extensionスキャン終了
                    temp_scan_pos = child_data_start_fl + child_size_fl
            # FrameListの内部を解析 (収集したBoneIDマップとcountsを渡す)
            parse_chunk(f, chunk_data_end, indent + "  ", parent_id=chunk_id, bone_id_map_for_frame_struct=collected_bone_ids, counts=counts, tsv_output=tsv_output)

        elif chunk_id == 0x11E and chunk_size > 0: # HAnim PLG (通常表示モード)
            if not tsv_output: parse_hanim_plg(f, chunk_size, indent + "  ", tsv_output=tsv_output)
            else: f.seek(chunk_data_end) # TSVモードではスキップ
        elif chunk_id == 0x02: # String
            parse_string_chunk(f, chunk_size, indent + "  ", tsv_output=tsv_output)
        elif chunk_id == 0x01 and parent_id == 0x14: # Struct in Atomic
            parse_atomic_struct(f, chunk_size, indent + "  ", counts, tsv_output=tsv_output)
        elif chunk_id == 0x01 and parent_id == 0x1A: # Struct in Geometry List
            parse_geometry_list_struct(f, chunk_size, indent + "  ", counts, tsv_output=tsv_output)
        elif chunk_id == 0x01 and parent_id == 0x08: # Struct in Material List
            parse_material_list_struct(f, chunk_size, indent + "  ", counts, tsv_output=tsv_output)
        elif chunk_id == 0x01 and parent_id == 0x07: # Struct in Material
            parse_material_struct(f, chunk_size, indent + "  ", counts, tsv_output=tsv_output)
        elif chunk_id == 0x01 and parent_id == 0x0E: # Struct in Frame List
            parse_frame_list_struct(f, chunk_size, indent + "  ", counts, bone_id_map_for_frame_struct, tsv_output=tsv_output) # 収集したマップとcountsを渡す
        elif is_container: # Other Container Chunks
             parse_chunk(f, chunk_data_end, indent + "  ", chunk_id, bone_id_map_for_frame_struct, counts, tsv_output=tsv_output) # マップとcountsを伝播
        else: # Non-Container Chunks or empty containers
            f.seek(chunk_data_end) # Skip data

        # --- End of Chunk Handling ---
        current_end_pos = f.tell()
        if current_end_pos > chunk_data_end:
            if not tsv_output: print(f"{indent}  Warning: Pointer (0x{current_end_pos:X}) beyond expected end (0x{chunk_data_end:X}) for '{chunk_name}'. Adjusting.")
            f.seek(chunk_data_end)
        elif current_end_pos < chunk_data_end:
            f.seek(chunk_data_end)

def analyze_dff(filepath, tsv_output=False):
    """DFFファイルを解析し、チャンク構造を出力またはTSVデータとして返す"""
    if not os.path.exists(filepath):
        if not tsv_output: print(f"Error: File not found at {filepath}")
        return None if tsv_output else None

    counts = {
        'frame_count': 0,
        'geometry_count': 0,
        'material_count': 0,
        'texture_count': 0,
        'atomic_count': 0,
    }

    try:
        with open(filepath, 'rb') as f:
            file_size = os.path.getsize(filepath)
            if not tsv_output:
                print(f"Analyzing DFF file: {filepath} (Size: {file_size} bytes)")
                print("-" * 30)
            parse_chunk(f, file_size, indent="" if tsv_output else "  ", counts=counts, tsv_output=tsv_output) # ファイル全体を解析, TSVモードならindentを空に
            if not tsv_output:
                print("-" * 30)
                print("Analysis complete.")

        if tsv_output:
            # ファイル名, Frame Count, Geometry Count, Material Count, Texture Count, Atomic Count
            return [
                os.path.basename(filepath),
                counts['frame_count'],
                counts['geometry_count'],
                counts['material_count'],
                counts['texture_count'],
                counts['atomic_count']
            ]
        else:
            return None # 通常出力モードではNoneを返す

    except IOError as e:
        if not tsv_output: print(f"Error opening/reading file {filepath}: {e}")
        return None if tsv_output else None
    except Exception as e:
        if not tsv_output:
            print(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
        return None if tsv_output else None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze RenderWare DFF files.')
    parser.add_argument('dff_file', nargs='*', help='Path(s) to the DFF file(s) to analyze.')
    parser.add_argument('-t', '--tsv', action='store_true', help='Output results in TSV format.')
    parser.add_argument('-o', '--output', help='Output TSV file path.')

    args = parser.parse_args()

    # デバッグ出力: args.dff_file の内容を確認
    # print(f"Debug: args.dff_file = {args.dff_file}", file=sys.stderr) # デバッグ出力は削除

    input_files = []
    if args.dff_file:
        for pattern in args.dff_file:
            # ワイルドカードが含まれているか確認し、globで展開
            if '*' in pattern or '?' in pattern:
                input_files.extend(glob.glob(pattern, recursive=True))
            else:
                input_files.append(pattern)

    if args.tsv:
        output_file = None
        if args.output:
            try:
                # ディレクトリが存在しない場合は作成
                output_dir = os.path.dirname(args.output)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                output_file = open(args.output, 'w', encoding='utf-8')
            except IOError as e:
                print(f"Error opening output file {args.output}: {e}", file=sys.stderr)
                sys.exit(1)

        # TSVヘッダーを出力
        header = "Filename\tFrame Count\tGeometry Count\tMaterial Count\tTexture Count\tAtomic Count"
        if output_file:
            output_file.write(header + '\n')
        else:
            print(header)

        if input_files:
            for dff_path in input_files:
                result = analyze_dff(dff_path, tsv_output=True)
                if result:
                    line = '\t'.join(map(str, result))
                    if output_file:
                        output_file.write(line + '\n')
                    else:
                        print(line)
        else:
            print("No DFF files found for TSV output.", file=sys.stderr)

        if output_file:
            output_file.close()

    else: # 通常の解析出力モード
        if input_files:
            for dff_path in input_files:
                analyze_dff(dff_path)
        else:
            print("Usage: python analyze_dff.py <path_to_dff_file> [-t|--tsv] [-o|--output <output_file>]")
            # テストファイルパスを修正し、ワイルドカード展開を考慮
            test_files = glob.glob("001_005_00003.dff", recursive=True)
            if test_files:
                 print(f"\n--- Running analysis on test file: {test_files[0]} ---")
                 analyze_dff(test_files[0])
            else:
                 print(f"Test file '001_005_00003.dff' not found. Provide path as argument.")
                 sys.exit(1)
