import struct
import os
import re
import configparser
from config_loader import load_config, get_path_from_config

# 設定読み込み
CONFIG_FILENAME = 'config.ini'
config, ini_dir = load_config(CONFIG_FILENAME)

def get_anim_filenames_from_metadata(metadata_path):
    """
    アニメーションメタデータファイル (バイナリ形式と仮定) からファイル名のリストを抽出する関数。
    パターン: 数字3桁_数字3桁_数字5桁_数字3桁.ame
    """
    filenames = []
    print(f"Extracting filenames from metadata using regex: {metadata_path}")
    filename_pattern = rb"(\d{3}_\d{3}_\d{5}_\d{3}\.ame)"

    try:
        with open(metadata_path, 'rb') as f_meta:
            metadata_content = f_meta.read()
            print(f"Read {len(metadata_content)} bytes from metadata file.")

            matches = re.findall(filename_pattern, metadata_content)

            if matches:
                print(f"Found {len(matches)} potential filenames matching the pattern.")
                for match_bytes in matches:
                    try:
                        filename_str = match_bytes.decode('ascii')
                        safe_filename = "".join(c for c in filename_str if c.isalnum() or c in ('_', '.', '-')).strip()
                        if safe_filename == filename_str:
                            filenames.append(safe_filename)
                        else:
                            print(f"  Warning: Filename potentially altered for safety: '{filename_str}' -> '{safe_filename}'")
                            filenames.append(safe_filename)
                    except UnicodeDecodeError:
                        print(f"  Warning: Skipping non-ASCII match: {match_bytes}")
            else:
                 print("Warning: No filenames matching the specified pattern found in the metadata file.")
                 print(f"         File checked: {metadata_path}")
                 print(f"         Pattern used: {filename_pattern.decode('ascii', errors='replace')}")

            print(f"Finished extracting filenames. Found {len(filenames)} valid names matching the pattern.")

    except FileNotFoundError:
        print(f"Error: Metadata file not found at {metadata_path}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during metadata filename extraction: {e}")
        return []

    return filenames

def extract_anim_files_rw_chunk(anim_data_path, output_dir, filenames):
    """
    アニメーション本体データをスキャンし、RenderWare Animationチャンク(ID 0x1B)
    に基づいてファイルを分割・保存する関数。
    (ファイルを一度に読み込むバージョン)
    """
    print(f"\nStarting Animation extraction based on RenderWare Chunk (ID: 0x1B) scan: {anim_data_path}")
    if not filenames:
        print("Error: No filenames provided from metadata. Cannot proceed.")
        return

    # 出力ディレクトリ作成
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        except OSError as e:
            print(f"Error creating output directory {output_dir}: {e}")
            return

    extracted_count = 0
    error_count = 0
    filename_index = 0

    # RenderWare Animationチャンク ID (0x1B)
    RW_ANIM_CHUNK_ID = b'\x1B\x00\x00\x00'
    HEADER_SIZE = 12 # ID(4) + BodySize(4) + Version(4)

    try:
        print(f"Reading animation data file into memory ({anim_data_path})...")
        with open(anim_data_path, 'rb') as f_anim_data:
            anim_content = f_anim_data.read()
        file_size = len(anim_content)
        print(f"Read {file_size} bytes.")

        if file_size == 0:
            print("Error: Animation data file is empty.")
            return

        chunk_positions = []
        current_pos = 0
        # 1. 全てのAnimationチャンク(0x1B)の位置を特定する
        print("Scanning for RenderWare Animation Chunks (ID: 0x1B)...")
        while True:
            # メモリ上の anim_content からチャンクIDを探す
            found_index = anim_content.find(RW_ANIM_CHUNK_ID, current_pos)
            if found_index != -1:
                # 新しく見つかった位置がリストの最後の要素より大きい場合のみ追加
                if not chunk_positions or found_index > chunk_positions[-1]:
                    chunk_positions.append(found_index)
                    # print(f"  Found Anim chunk header at offset: {found_index}")
                # 次の検索は、見つかった位置の1バイト後から開始
                current_pos = found_index + 1
            else:
                # これ以上見つからなければループ終了
                break

        print(f"Finished scanning. Found {len(chunk_positions)} Animation Chunk headers (0x1B).")

        # 2. チャンク位置に基づいてファイルを切り出す
        if not chunk_positions:
            print("Error: No RenderWare Animation Chunks (ID: 0x1B) found in the data file.")
            return

        # ファイル名リストとチャンク数の比較・警告
        if len(chunk_positions) > len(filenames):
             print(f"Warning: Found {len(chunk_positions)} Anim chunks, but only {len(filenames)} filenames provided. Extracting only the first {len(filenames)} chunks.")
        elif len(chunk_positions) < len(filenames):
             print(f"Warning: Found only {len(chunk_positions)} Anim chunks, but {len(filenames)} filenames provided. Some filenames will not be used.")

        print("\nStarting file extraction...")
        for i in range(len(chunk_positions)):
            # 利用可能なファイル名がなくなったら終了
            if filename_index >= len(filenames):
                print(f"Reached end of filename list (processed {filename_index} names). Stopping extraction.")
                break

            header_start_pos = chunk_positions[i]

            # ヘッダ全体(12バイト)がファイル内に収まっているか確認
            if header_start_pos + HEADER_SIZE > file_size:
                print(f"\nWarning: Found chunk header at {header_start_pos}, but not enough data for full header. Skipping.")
                error_count += 1
                continue

            # ヘッダデータ(12バイト)をメモリから取得
            header_data = anim_content[header_start_pos : header_start_pos + HEADER_SIZE]

            # ボディサイズを読み取る (リトルエンディアン)
            try:
                # ヘッダの [4:8] バイトがボディサイズ
                chunk_body_size = struct.unpack('<I', header_data[4:8])[0]
                # version = struct.unpack('<I', header_data[8:12])[0] # 必要ならバージョンも取得
                print(f"\nExtracting chunk {filename_index + 1} / {min(len(chunk_positions), len(filenames))}:")
                print(f"  Offset: {header_start_pos}")
                print(f"  Chunk Body Size: {chunk_body_size}")
            except struct.error as e:
                print(f"\nWarning: Error unpacking chunk size at offset {header_start_pos + 4}: {e}. Skipping.")
                error_count += 1
                continue

            # アニメーションチャンク全体のサイズ = ヘッダサイズ + ボディサイズ
            total_chunk_size = HEADER_SIZE + chunk_body_size

            # サイズチェック
            if total_chunk_size <= HEADER_SIZE: # ボディサイズが0以下はおかしい
                print(f"  Warning: Invalid chunk size (Body Size <= 0). Skipping.")
                error_count += 1
                continue

            # チャンクの終了位置がファイルサイズを超えないかチェック
            chunk_end_pos = header_start_pos + total_chunk_size
            adjusted_size = False
            if chunk_end_pos > file_size:
                 print(f"  Warning: Calculated chunk end position ({chunk_end_pos}) exceeds file size ({file_size}). Adjusting size to read until EOF.")
                 total_chunk_size = file_size - header_start_pos # ファイル末尾まで読み取る
                 adjusted_size = True
                 if total_chunk_size < HEADER_SIZE:
                     print("  Error: Adjusted size is smaller than header size. Skipping.")
                     error_count += 1
                     continue

            # ファイル名を取得して出力パスを生成
            current_filename = filenames[filename_index]
            output_path = os.path.join(output_dir, current_filename)
            print(f"  Total Chunk Size: {total_chunk_size}{' (adjusted)' if adjusted_size else ''}")
            print(f"  Filename: {current_filename}")
            print(f"  Output: {output_path}")

            try:
                # データ切り出し (メモリから) と保存
                chunk_content = anim_content[header_start_pos : header_start_pos + total_chunk_size]
                extracted_size = len(chunk_content)

                if extracted_size != total_chunk_size:
                     # サイズ調整した場合、ここは警告にならないようにする
                     if not adjusted_size:
                          print(f"  Warning: Extracted {extracted_size} bytes, expected {total_chunk_size}.")
                     else:
                          print(f"  Info: Extracted {extracted_size} bytes (adjusted to EOF).")
                if extracted_size == 0:
                     print("  Error: Extracted 0 bytes. Skipping.")
                     error_count += 1
                     continue

                with open(output_path, 'wb') as f_out:
                    f_out.write(chunk_content)
                print(f"  Successfully saved {extracted_size} bytes.")
                extracted_count += 1
                filename_index += 1 # 次のファイル名へ

            except IOError as e:
                print(f"  Error writing file {current_filename}: {e}")
                error_count += 1
            except Exception as e:
                print(f"  An unexpected error occurred processing {current_filename}: {e}")
                error_count += 1

        # --- サマリー表示 ---
        print("-" * 30)
        print(f"Extraction summary (RW Anim Chunk Scan - In Memory):")
        print(f"  Successfully extracted: {extracted_count} files based on 0x1B chunks")
        print(f"  Errors during extraction: {error_count}")
        print(f"  Filenames processed:  {filename_index}/{len(filenames)}")

    except FileNotFoundError:
        print(f"Error: Animation data file not found at {anim_data_path}")
    except MemoryError:
        print(f"Error: Not enough memory to read the entire animation data file ({anim_data_path}) at once.")
    except OSError as e:
         print(f"Error opening or reading the Animation data file {anim_data_path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during the extraction process: {e}")


# --- スクリプト実行部分 ---
if __name__ == "__main__":
    # === ファイルパス設定 ===
    metadata_file = get_path_from_config(config, ini_dir, 'AnimExtraction', 'metadata_file')
    anim_combined_data_file = get_path_from_config(config, ini_dir, 'AnimExtraction', 'archive_file')
    output_directory = get_path_from_config(config, ini_dir, 'AnimExtraction', 'output_dir', is_dir=True, create_dir=True)
    # === 設定ここまで ===

    print("="*50)
    print(" Animation File Extraction Script (RW Chunk Scan + Regex Filenames)")
    print("="*50)
    print(f"Metadata file:          {os.path.abspath(metadata_file)}")
    print(f"Animation data file:    {os.path.abspath(anim_combined_data_file)}")
    print(f"Output directory:       {os.path.abspath(output_directory)}")
    print("-" * 50)

    # 必要なファイルが存在するかチェック
    if not os.path.exists(metadata_file):
        print(f"Error: Metadata file '{metadata_file}' not found.")
    elif not os.path.exists(anim_combined_data_file):
         print(f"Error: Animation combined data file '{anim_combined_data_file}' not found.")
    else:
        # 1. メタデータからファイル名リストを取得
        filenames = get_anim_filenames_from_metadata(metadata_file)
        # 2. RenderWare Animationチャンク(0x1B)でスキャン・分割を実行
        if filenames:
             extract_anim_files_rw_chunk(anim_combined_data_file, output_directory, filenames)
        else:
             print("\nExiting script because no valid filenames were extracted from the metadata.")

    print("-" * 50)
    print("Script finished.")