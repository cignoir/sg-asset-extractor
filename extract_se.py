import struct
import os
import re
import configparser
from config_loader import load_config, get_path_from_config

# 設定読み込み
CONFIG_FILENAME = 'config.ini'
config, ini_dir = load_config(CONFIG_FILENAME)

def get_wav_filenames_from_metadata(metadata_path):
    """
    メタデータファイル (バイナリ) から正規表現を使ってWAV/SGTファイル名のリストを抽出する関数。
    """
    filenames = []
    print(f"Extracting filenames from metadata using regex: {metadata_path}")
    # パターン例: 000_000_00001.wav, 100_011_00047.sgt
    # 数字の桁数は可変とし、拡張子を .wav または .sgt に限定
    filename_pattern = rb"(\d+_\d+_\d+\.(?:wav|sgt))"

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
                        # ファイル名として使えない文字を置換 (念のため)
                        safe_filename = "".join(c for c in filename_str if c.isalnum() or c in ('_', '.', '-')).strip()
                        if safe_filename == filename_str: # パターンに合致していれば通常は問題ないはず
                             filenames.append(safe_filename)
                             # print(f"  Added filename: {safe_filename}") # デバッグ用
                        else:
                             print(f"  Warning: Filename potentially altered for safety: '{filename_str}' -> '{safe_filename}'")
                             filenames.append(safe_filename) # 変更後の名前を追加
                    except UnicodeDecodeError:
                        print(f"  Warning: Skipping non-ASCII match: {match_bytes}")
            else:
                 print("Warning: No filenames matching the specified pattern found in the metadata file.")
                 print(f"         File checked: {metadata_path}")
                 print(f"         Pattern used: {filename_pattern.decode('ascii', errors='replace')}")
                 print("         If filenames exist in a different format, please adjust the 'filename_pattern' variable.")

            print(f"Finished extracting filenames. Found {len(filenames)} valid names matching the pattern.")

    except FileNotFoundError:
        print(f"Error: Metadata file not found at {metadata_path}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during metadata filename extraction: {e}")
        return []

    return filenames


def extract_wav_files(wav_data_path, output_dir, filenames):
    """
    WAV本体データをスキャンし、RIFFヘッダに基づいてファイルを分割・保存する関数。
    ファイル名は提供されたリストを順番に使用する。
    """
    print(f"\nStarting WAV extraction based on RIFF header scan: {wav_data_path}")
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
    current_pos = 0 # WAV本体データ内の現在のスキャン位置

    try:
        with open(wav_data_path, 'rb') as f_wav_data:
            file_size = os.path.getsize(wav_data_path)
            print(f"Total size of WAV data file: {file_size} bytes")

            while current_pos < file_size:
                f_wav_data.seek(current_pos)
                # まずRIFF ID (4バイト) を読む
                riff_id = f_wav_data.read(4)
                if len(riff_id) < 4:
                    if len(riff_id) > 0: # ファイル末尾にRIFF ID未満のデータが残っている場合
                        print(f"Reached end of file with {len(riff_id)} remaining bytes.")
                    break # ファイル終端

                if riff_id == b'RIFF':
                    # RIFFヘッダが見つかった場合、サイズ情報 (次の4バイト) + WAVE ID等(4バイト)を読む
                    header_rest = f_wav_data.read(8) # Size(4) + Format(4)
                    if len(header_rest) < 8:
                         print(f"Warning: Found RIFF at {current_pos}, but cannot read full header (size/format). Skipping.")
                         current_pos += 4 # RIFF ID分だけ進む
                         continue

                    try:
                        # chunk_size は RIFFヘッダのID(4) + Size(4) を除く、ファイル全体のサイズ
                        chunk_size_bytes = header_rest[0:4]
                        chunk_size = struct.unpack('<I', chunk_size_bytes)[0]
                        # WAVファイル全体のサイズは chunk_size + 8
                        total_wav_size = chunk_size + 8
                        # WAVE ID (通常 'WAVE')
                        wave_id = header_rest[4:8]

                        print(f"\nFound RIFF header at offset: {current_pos}")
                        print(f"  Declared chunk size (file size - 8): {chunk_size}, Calculated Total WAV size: {total_wav_size}")
                        if wave_id == b'WAVE':
                            print("  Format: WAVE")
                        else:
                            print(f"  Format: {wave_id} (Not standard WAVE, but processing anyway)")


                        # サイズの妥当性チェック
                        if total_wav_size <= 12: # RIFF(4)+Size(4)+WAVE(4) より小さいのはおかしい
                            print(f"  Warning: Invalid total size ({total_wav_size}) calculated (must be > 12). Skipping this RIFF header.")
                            current_pos += 1 # 1バイトずらして再検索
                            continue
                        if current_pos + total_wav_size > file_size:
                            print(f"  Warning: Calculated WAV end position ({current_pos + total_wav_size}) exceeds data file size ({file_size}). Adjusting size.")
                            total_wav_size = file_size - current_pos # 残り全部を読み取る
                            if total_wav_size <= 0:
                                print("  Error: Adjusted size is zero or negative. Stopping.")
                                break

                        # ファイル名を取得
                        if filename_index >= len(filenames):
                            print(f"Error: Found more RIFF chunks ({extracted_count + 1}) than filenames ({len(filenames)}). Stopping extraction.")
                            error_count += 1
                            break

                        current_filename = filenames[filename_index]
                        # ファイル名の拡張子を確認 (ファイルの種類が混在している場合のため)
                        expected_ext = ".wav" if wave_id == b'WAVE' else ".bin" # WAVEでなければ .bin とする (仮)
                        if not current_filename.lower().endswith(expected_ext) and expected_ext == ".wav":
                             print(f"Warning: Filename '{current_filename}' from metadata does not end with expected '.wav'.")
                        elif not current_filename.lower().endswith(".sgt") and wave_id != b'WAVE':
                             # sgt ファイルのRIFF構造は不明なため、警告のみ
                             print(f"Warning: Filename '{current_filename}' doesn't end with .sgt, but RIFF chunk format is not 'WAVE'.")


                        output_path = os.path.join(output_dir, current_filename)
                        print(f"  Attempting to save as: {output_path} (Size: {total_wav_size})")

                        # WAVデータを読み込んで保存
                        f_wav_data.seek(current_pos) # ヘッダの先頭に戻る
                        wav_content = f_wav_data.read(total_wav_size)
                        read_size = len(wav_content)

                        if read_size != total_wav_size:
                            print(f"  Warning: Read {read_size} bytes, expected {total_wav_size}. File might be truncated.")
                        if read_size == 0:
                             print("  Error: Read 0 bytes. Skipping.")
                             error_count += 1
                             current_pos += 1 # 1バイト進めて再試行
                             continue

                        with open(output_path, 'wb') as f_out:
                            f_out.write(wav_content)
                        print(f"  Successfully saved {read_size} bytes to: {output_path}")
                        extracted_count += 1
                        filename_index += 1

                        # 次の検索開始位置へ (現在のWAVファイルの直後)
                        current_pos += total_wav_size

                    except struct.error as e:
                        print(f"  Error unpacking size at offset {current_pos + 4}: {e}. Skipping.")
                        current_pos += 1
                    except IOError as e:
                         print(f"  Error reading/writing file {current_filename}: {e}")
                         error_count += 1
                         current_pos += 1
                    except Exception as e:
                         print(f"  An unexpected error occurred processing RIFF chunk at {current_pos}: {e}")
                         error_count += 1
                         current_pos += 1

                else:
                    # RIFFヘッダではなかった -> 次のバイトへ
                    # print(f"No RIFF at {current_pos}") # デバッグ用
                    current_pos += 1

            # --- ループ終了後のサマリー表示 ---
            print("-" * 30)
            print(f"Extraction summary (RIFF Scan):")
            print(f"  Successfully extracted: {extracted_count} files")
            print(f"  Errors/Warnings during scan: {error_count}") # エラーカウント名を変更
            print(f"  Filenames processed: {filename_index}/{len(filenames) if filenames else 'N/A'}")

            # ファイル数とファイル名リストの数の比較
            if filenames: # ファイル名リストがある場合のみ比較
                if extracted_count < len(filenames):
                    print(f"Warning: Extracted {extracted_count} files, but {len(filenames)} filenames were found in metadata.")
                    print("         Some files listed in metadata might not have been found in the data file, or errors occurred.")
                elif extracted_count > len(filenames):
                    print(f"Warning: Extracted {extracted_count} files, which is MORE than the {len(filenames)} filenames found in metadata.")
                    print("         The data file might contain extra RIFF chunks not listed in the metadata.")

    except FileNotFoundError:
        print(f"Error: WAV data file not found at {wav_data_path}")
    except OSError as e:
         print(f"Error opening or reading the WAV data file {wav_data_path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during the extraction process: {e}")


# --- スクリプト実行部分 ---
if __name__ == "__main__":
    # === ファイル名を設定 ===
    metadata_file = get_path_from_config(config, ini_dir, 'SEExtraction', 'metadata_file')
    wav_combined_data_file = get_path_from_config(config, ini_dir, 'SEExtraction', 'archive_file')
    output_directory = get_path_from_config(config, ini_dir, 'SEExtraction', 'output_dir', is_dir=True, create_dir=True)
    # === 設定ここまで ===

    print("="*50)
    print(" WAV/SGT File Extraction Script (RIFF Scan + Metadata Filenames)")
    print("="*50)
    print(f"Metadata file:          {os.path.abspath(metadata_file)}")
    print(f"WAV combined data file: {os.path.abspath(wav_combined_data_file)}")
    print(f"Output directory:       {os.path.abspath(output_directory)}")
    print("-" * 50)

    # 必要なファイルが存在するかチェック
    if not os.path.exists(metadata_file):
        print(f"Error: Metadata file '{metadata_file}' not found.")
        print(f"       Please ensure the file exists or update the 'metadata_file' variable.")
    elif not os.path.exists(wav_combined_data_file):
         print(f"Error: WAV combined data file '{wav_combined_data_file}' not found.")
         print(f"       Please ensure the file exists or update the 'wav_combined_data_file' variable.")
    else:
        # 1. メタデータからファイル名リストを取得
        filenames = get_wav_filenames_from_metadata(metadata_file)
        # 2. RIFFスキャンを実行してファイル名を付けて保存
        if filenames: # ファイル名リストが空でなければ実行
             extract_wav_files(wav_combined_data_file, output_directory, filenames)
        else:
             print("Exiting script because no valid filenames were extracted from the metadata.")

    print("-" * 50)
    print("Script finished.")