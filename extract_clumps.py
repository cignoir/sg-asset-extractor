# extract_clumps.py
# -*- coding: utf-8 -*-
# Clump_*.bin ファイルからチャンク情報を読み取り、
# ClumpInfo_*.bin ファイルの情報を元に個別のDFFファイルを抽出します。
# 設定は config.ini から読み込みます。

import struct
import os
import re
import sys
import configparser
from config_loader import load_config, get_path_from_config

def get_filenames_from_metadata(metadata_path):
    """メタデータファイルから正規表現でDFFファイル名を抽出します。"""
    filenames = []
    # ファイル名パターン (例: 000_000_00000.dff)
    filename_pattern = rb"(\d{3}_\d{3}_\d{5}\.dff)"
    print(f"メタデータからファイル名を抽出中 (パターン: \\d{{3}}_\\d{{3}}_\\d{{5}}\\.dff): {metadata_path}")
    try:
        with open(metadata_path, 'rb') as f_meta:
            metadata_content = f_meta.read()
            matches = re.findall(filename_pattern, metadata_content)
            if matches:
                for match_bytes in matches:
                    try: filenames.append(match_bytes.decode('ascii'))
                    except UnicodeDecodeError: print(f"  警告: ASCIIデコード不能なファイル名スキップ: {match_bytes}")
                print(f"  {len(filenames)} 件のファイル名を抽出しました。")
            else:
                 print(f"警告: 指定されたパターンのファイル名がメタデータに見つかりません。")
    except FileNotFoundError: print(f"エラー: メタデータファイルが見つかりません: {metadata_path}"); return []
    except Exception as e: print(f"エラー: メタデータ読み込み中: {e}"); return []
    return filenames

def extract_dff_using_chunk_scan(dff_data_path, output_dir, filenames):
    """DFFデータファイルをスキャンし、Clumpチャンクを個別のDFFファイルとして保存します。"""
    print(f"\nDFFチャンクスキャンを開始: {dff_data_path}")
    if not filenames: print("エラー: メタデータからファイル名が提供されなかったため、抽出できません。"); return

    # RenderWare Clumpチャンクヘッダ (ID: 0x10)
    CLUMP_CHUNK_ID = b'\x10\x00\x00\x00'
    HEADER_SIZE = 12 # ID(4) + Size(4) + Version(4)
    SCAN_BUFFER_SIZE = 10 * 1024 * 1024 # 読み込みバッファサイズ

    extracted_count = 0; error_count = 0; filename_index = 0
    try:
        with open(dff_data_path, 'rb') as f_dff_data:
            file_size = os.path.getsize(dff_data_path)
            print(f"DFFデータファイルサイズ: {file_size} bytes")
            buffer = b''; buffer_start_offset = 0; eof_reached = False

            while True:
                # 必要ならバッファにデータを補充
                if not eof_reached and len(buffer) < SCAN_BUFFER_SIZE:
                    read_start = buffer_start_offset + len(buffer); f_dff_data.seek(read_start)
                    new_data = f_dff_data.read(SCAN_BUFFER_SIZE - len(buffer))
                    if new_data: buffer += new_data
                    else: eof_reached = True

                # バッファが空でEOFなら終了
                if not buffer and eof_reached: print("ファイル終端に到達しました。スキャン完了。"); break

                # ClumpチャンクIDを検索
                found_index_in_buffer = buffer.find(CLUMP_CHUNK_ID)

                if found_index_in_buffer != -1:
                    header_start_pos = buffer_start_offset + found_index_in_buffer
                    print(f"\nClumpヘッダ候補を発見: オフセット {header_start_pos}")

                    # ヘッダ全体がバッファ内にあるか確認
                    if found_index_in_buffer + HEADER_SIZE > len(buffer):
                        if eof_reached: print("  エラー: ファイル終端付近でヘッダ発見、データ不足。"); break
                        # ヘッダが境界をまたぐ可能性 -> 不要部分を捨てて再読み込み
                        discard_size = found_index_in_buffer; buffer = buffer[discard_size:]; buffer_start_offset += discard_size; continue

                    # ヘッダからチャンクサイズを読み取り
                    header_data = buffer[found_index_in_buffer : found_index_in_buffer + HEADER_SIZE]
                    try: chunk_body_size = struct.unpack('<I', header_data[4:8])[0]
                    except struct.error: print(f"  エラー: チャンクサイズ読み取り失敗 ({header_start_pos})。スキップ。"); advance = found_index_in_buffer + 1; buffer = buffer[advance:]; buffer_start_offset += advance; continue

                    total_dff_size = HEADER_SIZE + chunk_body_size
                    if total_dff_size <= 0: print(f"  警告: DFFサイズが無効 ({total_dff_size})。スキップ。"); advance = found_index_in_buffer + 1; buffer = buffer[advance:]; buffer_start_offset += advance; continue

                    # ファイルサイズを超えていないか、超えていたら調整
                    dff_end_pos = header_start_pos + total_dff_size; adjusted_size = False
                    if dff_end_pos > file_size:
                         print(f"  警告: 計算上のDFF終端({dff_end_pos})がファイルサイズ({file_size})を超過。サイズ調整。")
                         total_dff_size = file_size - header_start_pos; adjusted_size = True
                         if total_dff_size < HEADER_SIZE: print("  エラー: サイズ調整後、ヘッダ分のデータも不足。"); break

                    # メタデータからファイル名を取得
                    if filename_index >= len(filenames): print(f"エラー: DFFチャンク({header_start_pos})に対するファイル名が不足。抽出停止。"); error_count += 1; break
                    current_filename = filenames[filename_index]
                    output_path = os.path.join(output_dir, current_filename)
                    print(f"  保存試行: {output_path} (サイズ: {total_dff_size}{' adjusted' if adjusted_size else ''})")

                    # DFFデータを読み込んで保存
                    try:
                        f_dff_data.seek(header_start_pos); dff_content = f_dff_data.read(total_dff_size); read_size = len(dff_content)
                        if read_size != total_dff_size: print(f"  警告: 読み込みバイト数({read_size})が期待値({total_dff_size})と不一致。")
                        if read_size == 0: print("  エラー: 0バイト読み込み。スキップ。"); error_count += 1; advance = found_index_in_buffer + 1; buffer = buffer[advance:]; buffer_start_offset += advance; continue
                        with open(output_path, 'wb') as f_out: f_out.write(dff_content)
                        print(f"  ✓ 保存成功: {output_path}")
                        extracted_count += 1; filename_index += 1
                        # バッファを進める
                        advance_abs = header_start_pos + total_dff_size; advance_in_buffer = advance_abs - buffer_start_offset
                        if advance_in_buffer < 0: advance_in_buffer = 0
                        buffer = buffer[advance_in_buffer:]; buffer_start_offset = advance_abs
                    except IOError as e: print(f"  エラー: ファイル R/W ({current_filename}): {e}"); error_count += 1; advance = found_index_in_buffer + 1; buffer = buffer[advance:]; buffer_start_offset += advance
                    except Exception as e: print(f"  予期せぬエラー ({current_filename}): {e}"); error_count += 1; advance = found_index_in_buffer + 1; buffer = buffer[advance:]; buffer_start_offset += advance
                else:
                    # バッファ内にヘッダが見つからなかった
                    if eof_reached: break # EOFなら終了
                    # バッファの古い部分を削除 (境界ヘッダを考慮)
                    discard_size = len(buffer) - (HEADER_SIZE - 1) if len(buffer) >= HEADER_SIZE else 0
                    if discard_size > 0: buffer = buffer[discard_size:]; buffer_start_offset += discard_size

            # ループ終了後のチェック
            if filenames and filename_index < len(filenames) and extracted_count > 0: print(f"警告: {len(filenames) - filename_index} 個のファイル名が未使用です。")
            elif filenames and extracted_count > len(filenames): print(f"警告: {extracted_count} 個のチャンクを抽出しましたが、ファイル名は {len(filenames)} 個しかありませんでした。")

    except FileNotFoundError: print(f"エラー: DFFデータファイルが見つかりません: {dff_data_path}")
    except OSError as e: print(f"エラー: DFFデータファイルのオープン/処理中: {e}")
    except Exception as e: print(f"予期せぬエラー (チャンクスキャン中): {e}")

    print("-" * 30); print(f"抽出結果:"); print(f"  成功: {extracted_count} ファイル"); print(f"  エラー/警告: {error_count}"); print(f"  使用ファイル名: {filename_index}/{len(filenames) if filenames else 'N/A'}")

# --- メイン処理 ---
if __name__ == "__main__":
    # 設定読み込み
    CONFIG_FILENAME = 'config.ini'
    config, ini_dir = load_config(CONFIG_FILENAME)
    metadata_file = get_path_from_config(config, ini_dir, 'ClumpExtraction', 'metadata_file')
    dff_combined_data_file = get_path_from_config(config, ini_dir, 'ClumpExtraction', 'data_file')
    output_directory = get_path_from_config(config, ini_dir, 'ClumpExtraction', 'output_dir', is_dir=True, create_dir=True)

    if not metadata_file or not dff_combined_data_file or not output_directory:
        print("エラー: 設定ファイルに必要なファイル/ディレクトリパスが不足しています。", file=sys.stderr); sys.exit(1)

    print("="*50); print(" DFF File Extraction Script (Configured)"); print("="*50)
    print(f"メタデータファイル:     {metadata_file}")
    print(f"DFF結合データファイル: {dff_combined_data_file}")
    print(f"出力ディレクトリ:       {output_directory}")
    print("-" * 50)

    # ファイル存在チェック
    if not os.path.exists(metadata_file): print(f"エラー: メタデータファイル '{metadata_file}' が見つかりません。")
    elif not os.path.exists(dff_combined_data_file): print(f"エラー: DFF結合データファイル '{dff_combined_data_file}' が見つかりません。")
    else:
        # 1. メタデータからファイル名取得
        filenames = get_filenames_from_metadata(metadata_file)
        # 2. チャンクスキャンでDFF抽出
        if filenames: extract_dff_using_chunk_scan(dff_combined_data_file, output_directory, filenames)
        else: print("メタデータから有効なファイル名が抽出できなかったため、処理を終了します。")

    print("-" * 50); print("スクリプト終了。")