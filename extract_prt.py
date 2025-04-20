import struct
import os
import re
import sys

def parse_metadata_final(metadata_binary, data_file_size):
    """
    最終確定した構造に基づいてメタデータを解析する:
    - 構造: [Filename]\0 [Meta Data (可変長)]
    - サイズ: ファイル名+\0 の後のバイト列の pos=18 から 4バイト (<I)
    - オフセット: ファイル名+\0 の後のバイト列の pos=22 から 4バイト (<I)
    """
    if not metadata_binary:
        print("Error: Metadata binary data is empty.", file=sys.stderr)
        return []

    metadata_list = []
    offset = 0 # 現在のメタデータファイル読み込み位置
    metadata_len = len(metadata_binary)
    entry_count = 0
    # メタデータ内の相対オフセット
    SIZE_POS = 18
    OFFSET_POS = 22
    # サイズとオフセットを読むために最低限必要なメタデータ長 (ファイル名+\0の後)
    MIN_META_LEN_AFTER_NAME = max(SIZE_POS, OFFSET_POS) + 4

    print(f"\n--- Parsing Metadata (Final Hypothesis: Size @{SIZE_POS}<I, Offset @{OFFSET_POS}<I after Filename+\\0) ---")

    while offset < metadata_len:
        entry_count += 1
        current_entry_start_offset = offset # デバッグ用: エントリ開始位置

        try:
            # 1. ファイル名の終わり (ヌル文字) を探す
            try:
                null_terminator_index = metadata_binary.index(b'\x00', offset)
            except ValueError:
                # ファイル末尾までにヌル文字が見つからない場合
                if offset < metadata_len:
                    print(f"Warning [Entry {entry_count}]: No null terminator found after offset {offset}. Skipping remaining {metadata_len - offset} bytes.", file=sys.stderr)
                else:
                    print(f"Reached end of metadata file cleanly after Entry {entry_count-1}.")
                break # パース終了

            # ファイル名部分を抽出・デコード
            filename_bytes = metadata_binary[offset:null_terminator_index]
            filename = filename_bytes.decode('ascii', errors='replace') # Best effort decoding

            # メタデータの開始位置 (ヌル文字の次)
            meta_start = null_terminator_index + 1

            # 2. サイズとオフセットを読むのに十分なデータがあるか確認
            if meta_start + MIN_META_LEN_AFTER_NAME > metadata_len:
                print(f"Warning [Entry {entry_count}]: Not enough data for metadata after '{filename}'. Need {MIN_META_LEN_AFTER_NAME} bytes from {meta_start}, got {metadata_len - meta_start}. Stopping.", file=sys.stderr)
                break # メタデータ不足のため終了

            # 3. サイズとオフセットの抽出 (確定した構造)
            try:
                # サイズ: 相対位置 SIZE_POS から 4バイト (<I)
                size_bytes = metadata_binary[meta_start + SIZE_POS : meta_start + SIZE_POS + 4]
                file_size = struct.unpack('<I', size_bytes)[0]

                # オフセット: 相対位置 OFFSET_POS から 4バイト (<I)
                offset_bytes = metadata_binary[meta_start + OFFSET_POS : meta_start + OFFSET_POS + 4]
                file_offset = struct.unpack('<I', offset_bytes)[0]

                # 主要情報を表示 (毎エントリだと多いので、エラー時やデバッグ時のみが良いかも)
                # print(f"Entry {entry_count}: File='{filename}', Size={file_size} (from {size_bytes.hex(' ')} @rel {SIZE_POS}), Offset={file_offset} (from {offset_bytes.hex(' ')} @rel {OFFSET_POS})")

                # 妥当性チェック
                valid_entry = True
                error_msg = []
                if file_offset >= data_file_size:
                    error_msg.append(f"Offset {file_offset} >= Data Size {data_file_size}")
                    valid_entry = False
                if file_size < 0: # 通常uint32では発生しないが一応
                    error_msg.append(f"Negative Size {file_size}")
                    valid_entry = False
                # サイズがデータサイズ全体より大きいのは異常として扱う
                if file_size > data_file_size and data_file_size > 0:
                    error_msg.append(f"Size {file_size} > Data Size {data_file_size}")
                    valid_entry = False
                # オフセット+サイズが範囲を超える場合は警告のみ
                elif file_offset + file_size > data_file_size:
                     warning_msg = f"Warning [Entry {entry_count}]: Offset+Size {file_offset + file_size} > Data Size {data_file_size} for '{filename}'. (Will be truncated)"
                     print(warning_msg, file=sys.stderr)
                elif file_size == 0:
                     info_msg = f"Info [Entry {entry_count}]: Zero size file '{filename}'."
                     # print(info_msg) # ゼロサイズは正常なのでログは任意

                if valid_entry:
                     metadata_list.append({
                         "filename": filename,
                         "offset": file_offset,
                         "size": file_size
                     })
                else:
                     # 無効なエントリの詳細を表示してスキップ
                     print(f"Error [Entry {entry_count}]: Invalid metadata for '{filename}'. Reason(s): {'; '.join(error_msg)}. Skipping.", file=sys.stderr)
                     print(f"  -> Details: SizeBytes={size_bytes.hex(' ')}, OffsetBytes={offset_bytes.hex(' ')}, Parsed Size={file_size}, Parsed Offset={file_offset}", file=sys.stderr)


            except struct.error as e:
                 print(f"Error [Entry {entry_count}]: unpacking metadata for '{filename}' (likely corrupt data near offset {meta_start}): {e}. Skipping.", file=sys.stderr)
            except IndexError:
                 # meta_start + MIN_META_LEN_AFTER_NAME チェックで通常は捕捉されるはず
                 print(f"Error [Entry {entry_count}]: accessing metadata bytes for '{filename}'. Corrupt? Skipping.", file=sys.stderr)

            # 4. 次のエントリの開始位置へ移動 (現在のファイル名のヌル文字の次から次のヌル文字を探し、その次のバイトへ)
            try:
                # 現在のヌル位置の次から検索を開始
                next_offset_search_start = null_terminator_index + 1
                if next_offset_search_start >= metadata_len:
                    # ファイル末尾なら終了
                    print(f"Info: Reached end of metadata after processing entry {entry_count}.")
                    break

                # 次のヌル文字を探す
                next_null_terminator_index = metadata_binary.index(b'\x00', next_offset_search_start)
                # 次のエントリは、見つかったヌル文字の次のバイトから
                offset = next_null_terminator_index + 1

                # 追加チェック：次のオフセットが現在のオフセットより進んでいることを確認
                if offset <= current_entry_start_offset:
                     print(f"Error [Entry {entry_count}]: Failed to advance offset, potential infinite loop detected near {offset}. Stopping.", file=sys.stderr)
                     break
                # 追加チェック：次のオフセットがファイル終端を超えないか確認
                if offset >= metadata_len:
                    print(f"Info: Next entry offset points to or beyond end of file after entry {entry_count}. Assuming end.")
                    break

            except ValueError:
                # これ以上ヌル文字が見つからない場合
                print(f"Info: No further null terminator found after entry {entry_count}. Assuming end of metadata.")
                break # パース終了

        except Exception as e:
            # ファイル名検索中の予期せぬエラーなど
            print(f"An critical error occurred parsing entry {entry_count} near offset {offset}: {e}", file=sys.stderr)
            break # 安全のため停止

    print(f"\nFinished parsing metadata. Found {len(metadata_list)} valid entries.")
    return metadata_list


# extract_files 関数 (変更なし、堅牢性は維持)
def extract_files(data_binary, metadata_list, output_dir="output/prt"):
    if not data_binary:
        print("Error: Binary data for extraction is missing.", file=sys.stderr)
        return 0, 0
    if not metadata_list:
        print("Info: Metadata list is empty. No files to extract.")
        return 0, 0
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"\nOutput directory: '{os.path.abspath(output_dir)}'")
    except OSError as e:
        print(f"Error creating output directory '{output_dir}': {e}", file=sys.stderr)
        return 0, len(metadata_list)

    data_len = len(data_binary)
    extracted_count = 0
    error_count = 0
    print("Starting file extraction...")

    for i, meta in enumerate(metadata_list):
        filename = meta["filename"]
        offset = meta["offset"]
        size = meta["size"]
        entry_num = i + 1

        safe_filename = re.sub(r'[\\/*?:"<>|\0]', '_', filename)
        output_path = os.path.join(output_dir, safe_filename)

        # メタデータ解析でチェック済みだが、最終確認
        if offset < 0 or size < 0 or offset >= data_len:
             print(f"Error [Entry {entry_num}]: Invalid offset/size detected before extraction for '{safe_filename}' (Off:{offset}, Size:{size}, DataLen:{data_len}). Skipping.", file=sys.stderr)
             error_count += 1
             continue
        # サイズがデータ全体より大きいのもエラー（parse_metadataでチェック済みのはず）
        if size > data_len and data_len > 0 :
             print(f"Error [Entry {entry_num}]: Invalid size detected before extraction for '{safe_filename}' (Size:{size}, DataLen:{data_len}). Skipping.", file=sys.stderr)
             error_count += 1
             continue

        # 抽出サイズの計算と調整
        effective_size = size
        if offset + size > data_len:
            effective_size = data_len - offset
            if effective_size < 0: effective_size = 0

        # ファイル抽出と書き込み
        try:
            if effective_size == 0:
                 # print(f"Info [Entry {entry_num}]: Creating empty file '{safe_filename}'.")
                 with open(output_path, 'wb') as f_out: pass
            else:
                 # print(f"Info [Entry {entry_num}]: Extracting '{safe_filename}' (Offset: {offset}, Size: {effective_size})...")
                 # メモリ使用量を考慮し、必要ならここを修正 (mmap または都度読み込み)
                 file_data = data_binary[offset : offset + effective_size]
                 with open(output_path, 'wb') as f_out:
                     f_out.write(file_data)
            extracted_count += 1
        except MemoryError:
             print(f"Error [Entry {entry_num}]: MemoryError extracting data for '{safe_filename}' (size: {effective_size}). Skipping.", file=sys.stderr)
             error_count += 1; file_data = None; import gc; gc.collect()
        except IOError as e:
            print(f"Error writing file '{output_path}': {e}", file=sys.stderr); error_count += 1
        except Exception as e:
            print(f"Error extracting '{safe_filename}': {e}", file=sys.stderr); error_count += 1

    print(f"Extraction finished. Success: {extracted_count}, Errors during extraction: {error_count}")
    return extracted_count, error_count


# --- メイン処理 ---
if __name__ == "__main__":
    metadata_bin_file = "bin/PrtInfo_011.bin"
    data_bin_file = "bin/Prt_011.bin"
    output_directory = "output/prt" # 出力先変更

    print("--- Starting File Extraction Process (Final Hypothesis v2) ---")
    print(f"Metadata file: '{metadata_bin_file}'")
    print(f"Data file:     '{data_bin_file}'")
    print(f"Output dir:    '{output_directory}'")

    # --- Step 1: Read Metadata ---
    print(f"\n[Step 1/3] Reading metadata binary file...")
    metadata_binary_data = None
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
        meta_path = os.path.join(script_dir, metadata_bin_file)
        with open(meta_path, 'rb') as f_meta: metadata_binary_data = f_meta.read()
        print(f"Successfully read metadata file. Size: {len(metadata_binary_data)} bytes.")
    except FileNotFoundError: sys.exit(f"Error: Metadata file not found at '{os.path.abspath(meta_path)}'")
    except Exception as e: sys.exit(f"Error reading metadata file '{meta_path}': {e}")

    # --- Step 2: Get Data File Size ---
    print(f"\n[Step 2/3] Determining data file size...")
    data_file_size = 0
    try:
        data_path = os.path.join(script_dir, data_bin_file)
        data_file_size = os.path.getsize(data_path)
        print(f"Successfully determined data file size: {data_file_size} bytes.")
    except FileNotFoundError: sys.exit(f"Error: Data file not found at '{os.path.abspath(data_path)}'")
    except Exception as e: sys.exit(f"Error accessing data file '{data_path}': {e}")
    if data_file_size <= 0: sys.exit(f"Error: Data file size is zero or invalid.")

    # --- Step 3: Parse Metadata (Final Hypothesis) ---
    print(f"\n[Step 3/3] Parsing metadata with final hypothesis...")
    metadata_info = parse_metadata_final(metadata_binary_data, data_file_size)

    # --- Step 4: Read Data & Extract ---
    if metadata_info:
        print(f"\n[Step 4/4] Reading data file and extracting...")
        data_binary_content = None
        try:
            # メモリ負荷を考慮し、全体を読み込むか判断
            # 今回は5MB程度なので読み込む
            print(f"Reading data file '{data_path}' into memory...")
            with open(data_path, 'rb') as f_data: data_binary_content = f_data.read()
            print(f"Successfully read data file.")

            output_path_full = os.path.join(script_dir, output_directory)
            success_count, error_count_extract = extract_files(data_binary_content, metadata_info, output_path_full)

            print("\n--- Final Summary ---")
            print(f"  Valid metadata entries found: {len(metadata_info)}")
            print(f"  Files successfully extracted: {success_count}")
            print(f"  Errors during extraction:   {error_count_extract}")
            print("---------------------")

        except FileNotFoundError: print(f"Error: Data file not found at '{os.path.abspath(data_path)}'", file=sys.stderr)
        except MemoryError: print(f"\nError: MemoryError reading data file '{data_path}'.", file=sys.stderr)
        except Exception as e: print(f"Error reading/extracting data file '{data_path}': {e}", file=sys.stderr)
    else:
        print("\nNo valid metadata entries found. No files were extracted.")

    print("\n--- File Extraction Process Finished ---")