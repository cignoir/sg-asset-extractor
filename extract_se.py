import struct
import os
import re

# === 関数定義 ===

def get_all_filenames_from_metadata(metadata_path):
    """
    メタデータファイルから全てのファイル名 (.wav および .sgt) を
    出現順に抽出する関数。
    """
    filenames = []
    print(f"Extracting all filenames from metadata: {metadata_path}")
    # パターン例: 000_000_00001.wav, 100_011_00047.sgt
    filename_pattern = rb"(\d+_\d+_\d+\.(?:wav|sgt))"
    try:
        with open(metadata_path, 'rb') as f_meta:
            metadata_content = f_meta.read()
            print(f"Read {len(metadata_content)} bytes.")
            matches = re.findall(filename_pattern, metadata_content)
            if matches:
                print(f"Found {len(matches)} total filenames matching pattern.")
                for match_bytes in matches:
                    try:
                        filename_str = match_bytes.decode('ascii')
                        safe_filename = "".join(c for c in filename_str if c.isalnum() or c in ('_', '.', '-')).strip()
                        if safe_filename:
                            filenames.append(safe_filename)
                        else:
                             print(f"  Warning: Empty or invalid filename generated from: {filename_str}")
                    except UnicodeDecodeError:
                         print(f"  Warning: Skipping non-ASCII match: {match_bytes}")
            else:
                 print("Warning: No filenames matching pattern found in metadata.")
                 print(f"         Pattern used: {filename_pattern.decode('ascii', errors='replace')}")

            print(f"Finished metadata scan. Extracted {len(filenames)} filenames.")
    except FileNotFoundError:
        print(f"Error: Metadata file not found at {metadata_path}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during metadata filename extraction: {e}")
        return []
    return filenames

def extract_se_files_by_riff_type(data_path, output_dir, all_filenames):
    """
    本体データをRIFFスキャンし、フォームタイプ(WAVE or DMSG/DMUS)に応じて
    メタデータのファイル名リスト(.wav用と.sgt用に分けて)から名前を割り当てて抽出する。
    """
    print(f"\nStarting SE file extraction (RIFF Scan by Type): {data_path}")
    if not all_filenames:
        print("Error: No filenames provided from metadata.")
        return

    # ファイル名リストを .wav と .sgt に分割 (順番は維持)
    wav_filenames = [name for name in all_filenames if name.lower().endswith(".wav")]
    sgt_filenames = [name for name in all_filenames if name.lower().endswith(".sgt")]
    print(f"Found {len(wav_filenames)} '.wav' and {len(sgt_filenames)} '.sgt' filenames in metadata.")

    # 出力ディレクトリ作成
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        except OSError as e:
            print(f"Error creating output directory {output_dir}: {e}")
            return

    extracted_wav_count = 0
    extracted_sgt_count = 0
    error_count = 0
    wav_filename_index = 0 # .wavリスト用インデックス
    sgt_filename_index = 0 # .sgtリスト用インデックス
    riff_chunks_found = 0

    # SGTファイルのフォームタイプ候補 (大文字/小文字を考慮しないようにバイトで定義)
    SGT_FORM_TYPE_DMSG = b'DMSG'
    SGT_FORM_TYPE_DMUS = b'DMUS' # こちらもチェック対象に入れるか？ まずはDMSGのみで試す

    try:
        with open(data_path, 'rb') as f_data:
            data_file_size = os.path.getsize(data_path)
            print(f"Scanning data file (Size: {data_file_size} bytes) for RIFF headers...")
            current_pos = 0

            while current_pos < data_file_size:
                f_data.seek(current_pos)
                riff_id = f_data.read(4)
                if len(riff_id) < 4: break

                if riff_id == b'RIFF':
                    riff_chunks_found += 1
                    header_rest = f_data.read(8) # Size(4) + Format(4)
                    if len(header_rest) < 8:
                        print(f"Warning: Found RIFF at offset {current_pos}, but incomplete header. Skipping.")
                        current_pos += 4
                        continue

                    try:
                        chunk_size = struct.unpack('<I', header_rest[0:4])[0]
                        form_type = header_rest[4:8]
                        total_file_size = chunk_size + 8

                        print(f"\nFound RIFF chunk #{riff_chunks_found} at offset: {current_pos}")
                        print(f"  Declared chunk size (file size - 8): {chunk_size}, Calculated Total size: {total_file_size}")
                        print(f"  Form Type: {form_type}")

                        # サイズ妥当性チェック
                        if total_file_size <= 8: # RIFF ID+Size より小さいのはおかしい
                            print(f"  Warning: Invalid total size ({total_file_size}). Skipping.")
                            error_count += 1
                            current_pos += 1 # 1バイトずらす
                            continue
                        if current_pos + total_file_size > data_file_size:
                            print(f"  Warning: Declared size exceeds EOF. Adjusting size.")
                            total_file_size = data_file_size - current_pos
                            if total_file_size <= 0:
                                print("  Error: Adjusted size is zero or negative. Stopping.")
                                break

                        current_filename = None
                        is_wav = False
                        is_sgt = False

                        # フォームタイプに応じてファイル名を割り当て
                        if form_type == b'WAVE':
                            if wav_filename_index < len(wav_filenames):
                                current_filename = wav_filenames[wav_filename_index]
                                is_wav = True
                            else:
                                print(f"Error: Found WAVE chunk but no more '.wav' filenames available (Index {wav_filename_index}). Stopping.")
                                error_count += 1
                                break
                        elif form_type == SGT_FORM_TYPE_DMSG or form_type == SGT_FORM_TYPE_DMUS: # DMSG または DMUS をチェック
                            if sgt_filename_index < len(sgt_filenames):
                                current_filename = sgt_filenames[sgt_filename_index]
                                is_sgt = True
                            else:
                                print(f"Error: Found {form_type} chunk but no more '.sgt' filenames available (Index {sgt_filename_index}). Stopping.")
                                error_count += 1
                                break
                        else:
                             print(f"  Warning: Unknown or unsupported RIFF Form Type '{form_type}'. Skipping this chunk.")
                             # 不明なチャンクをスキップ
                             current_pos += max(1, total_file_size) if total_file_size > 0 else 1
                             continue

                        # ファイル名が割り当てられた場合のみ処理
                        if current_filename:
                            output_path = os.path.join(output_dir, current_filename)
                            print(f"  Assigning filename: {current_filename}")
                            print(f"  Attempting to save as: {output_path} (Size: {total_file_size})")

                            # 抽出と保存
                            f_data.seek(current_pos)
                            content = f_data.read(total_file_size)
                            read_size = len(content)

                            if read_size != total_file_size: print(f"  Warning: Read {read_size} bytes, expected {total_file_size}.")
                            if read_size == 0:
                                 print("  Error: Read 0 bytes. Skipping file.")
                                 error_count += 1
                                 current_pos += 1
                                 # ファイル名インデックスは進めない
                                 continue

                            with open(output_path, 'wb') as f_out:
                                f_out.write(content)
                            print(f"  Successfully saved {read_size} bytes.")

                            # カウントとインデックスを進める
                            if is_wav:
                                extracted_wav_count += 1
                                wav_filename_index += 1
                            elif is_sgt:
                                extracted_sgt_count += 1
                                sgt_filename_index += 1

                            # 次の検索位置へ
                            current_pos += total_file_size

                        else: # このフローには通常到達しないはず
                             print(f"  Internal logic error: Filename not assigned for chunk at {current_pos}. Skipping.")
                             error_count += 1
                             current_pos += max(1, total_file_size) if total_file_size > 0 else 1


                    except struct.error as e:
                        print(f"  Error unpacking RIFF size at offset {current_pos + 4}: {e}. Skipping.")
                        error_count += 1
                        current_pos += 1
                    except IOError as e:
                         print(f"  Error reading/writing file {current_filename if current_filename else 'N/A'}: {e}")
                         error_count += 1
                         current_pos += 1
                    except Exception as e:
                         print(f"  Unexpected error processing RIFF chunk at {current_pos}: {e}")
                         error_count += 1
                         current_pos += 1
                else:
                    # RIFFヘッダではなかった場合、1バイト進める
                    current_pos += 1

            print(f"\nFinished scanning data file. Found {riff_chunks_found} RIFF chunks total.")

    except FileNotFoundError:
        print(f"Error: Data file not found at {data_path}")
        return
    except OSError as e:
        print(f"Error opening or reading the data file {data_path}: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    # --- 最終サマリー ---
    print("-" * 30)
    print(f"Extraction Summary (RIFF Scan by Type):")
    print(f"  Successfully extracted: {extracted_wav_count} WAV files, {extracted_sgt_count} SGT files (Total: {extracted_wav_count + extracted_sgt_count})")
    print(f"  Total RIFF chunks found: {riff_chunks_found}")
    print(f"  Total '.wav' filenames in metadata: {len(wav_filenames)}")
    print(f"  Total '.sgt' filenames in metadata: {len(sgt_filenames)}")
    print(f"  Errors encountered: {error_count}")
    # ファイル数とファイル名リストの数の比較に関する警告
    if extracted_wav_count != len(wav_filenames):
        print("Warning: The number of extracted WAV files does not match the number of '.wav' filenames in the metadata.")
    if extracted_sgt_count != len(sgt_filenames):
        print("Warning: The number of extracted SGT files does not match the number of '.sgt' filenames in the metadata.")


# --- スクリプト実行部分 ---
if __name__ == "__main__":
    # === ファイル名を設定 ===
    metadata_file = 'bin/SEInfo_002.bin'
    combined_data_file = 'bin/SE_002.bin'
    output_directory = 'output/se' # 出力ディレクトリ名変更
    # === 設定ここまで ===

    print("="*50)
    print(" SE File Extraction Script (RIFF Scan by Type + Metadata Filenames)")
    print("="*50)
    print(f"Metadata file:          {os.path.abspath(metadata_file)}")
    print(f"Combined data file:     {os.path.abspath(combined_data_file)}")
    print(f"Output directory:       {os.path.abspath(output_directory)}")
    print("-" * 50)

    if not os.path.exists(metadata_file):
        print(f"Error: Metadata file '{metadata_file}' not found.")
    elif not os.path.exists(combined_data_file):
         print(f"Error: Combined data file '{combined_data_file}' not found.")
    else:
        # 1. メタデータから全てのファイル名を取得
        all_filenames = get_all_filenames_from_metadata(metadata_file)
        # 2. RIFFタイプに基づいてファイルを抽出・保存
        if all_filenames:
             extract_se_files_by_riff_type(combined_data_file, output_directory, all_filenames)
        else:
             print("\nExiting script because no filenames were extracted from the metadata.")

    print("-" * 50)
    print("Script finished.")