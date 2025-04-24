# extract_textures.py
# -*- coding: utf-8 -*-
# TextureStream_*.bin アーカイブからテクスチャを抽出し、
# TextureInfo_*.bin メタデータの情報を元にPNGファイルとして保存します。
# フォーマットはヘッダフラグに基づいて自動判別します。
# コマンドライン引数からパスを受け取ります。

import struct
import numpy as np
from PIL import Image
import sys
import os
import glob # Added for file pattern matching
import argparse # Added for command-line argument parsing
from collections import defaultdict
# Removed configparser and config_loader imports

# --- 定数 ---
EXPECTED_HEADER_SIZE = 56
RGB565_BPP = 2; ARGB4444_BPP = 2
HEADER_WIDTH_OFFSET = 4; HEADER_HEIGHT_OFFSET = 8
HEADER_FORMAT_FLAG_OFFSET = 40; HEADER_FORMAT_FLAG_LEN = 4
FORMAT_FLAG_RGB565 = b'\x04\x02\x00\x00'
FORMAT_FLAG_ARGB4444 = b'\x04\x03\x00\x00' # ARGB4444

# --- 変換関数 ---
def convert_rgb565_to_rgb888(data_bytes, width, height):
    """RGB565 (LE) バイトデータを RGB888 NumPy 配列に変換します。"""
    expected_size = width * height * RGB565_BPP; img_array = np.zeros((height, width, 3), dtype=np.uint8)
    if len(data_bytes) < expected_size: raise ValueError("ピクセルデータサイズ不足")
    if len(data_bytes) > expected_size: data_bytes = data_bytes[:expected_size]
    pixels_16bit = struct.unpack(f'<{width * height}H', data_bytes)
    for i, p in enumerate(pixels_16bit): r5=(p>>11)&0x1F; g6=(p>>5)&0x3F; b5=p&0x1F; r8=(r5*255+15)//31; g8=(g6*255+31)//63; b8=(b5*255+15)//31; row,col=divmod(i,width); img_array[row,col]=[r8,g8,b8]
    return img_array

def convert_argb4444_to_rgba8888(data_bytes, width, height):
    """ARGB4444 (LE) バイトデータを RGBA8888 NumPy 配列に変換します。"""
    expected_size = width * height * ARGB4444_BPP; img_array = np.zeros((height, width, 4), dtype=np.uint8)
    if len(data_bytes) < expected_size: raise ValueError("ピクセルデータサイズ不足")
    if len(data_bytes) > expected_size: data_bytes = data_bytes[:expected_size]
    pixels_16bit = struct.unpack(f'<{width * height}H', data_bytes)
    for i,p in enumerate(pixels_16bit): a4=(p>>12)&0x0F; r4=(p>>8)&0x0F; g4=(p>>4)&0x0F; b4=p&0x0F; r8=r4*17; g8=g4*17; b8=b4*17; a8=a4*17; row,col=divmod(i,width); img_array[row,col]=[r8,g8,b8,a8]
    return img_array

# --- メタデータ解析関数 ---
def parse_metadata(metadata_path):
    """メタデータファイルを解析し、エントリ(ファイル名, サイズ, オフセット)のリストを返します。"""
    entries = []; METADATA_FORMAT_BYTES_LEN = 14
    print(f"メタデータ解析中: '{metadata_path}'")
    try:
        with open(metadata_path, 'rb') as f:
            while True: # 各エントリを処理するループ
                start_pos=f.tell(); filename_bytes=bytearray()
                # ファイル名読み取り (Null終端まで)
                while True: # ファイル名を1バイトずつ読むループ
                    byte = f.read(1)
                    if not byte: # ファイル終端ならリストを返して終了
                        return entries
                    if byte == b'\x00': # Null文字ならファイル名終了
                        break
                    filename_bytes.append(byte[0]) # ファイル名に追加

                filename=filename_bytes.decode('ascii', errors='ignore')
                # 空読み後のEOFチェック (必須)
                if not filename_bytes:
                    peek = f.peek(1) # 次のバイトを覗き見
                    if not peek: # 次がなければ真のEOF
                        return entries

                # 不明な14バイトをスキップ
                format_bytes_skipped=f.read(METADATA_FORMAT_BYTES_LEN)
                if len(format_bytes_skipped)<METADATA_FORMAT_BYTES_LEN:
                    print(f"警告: スキップ中にEOF ({filename})。"); return entries

                # サイズ, 未知パラメータ, オフセット読み取り
                data_chunk=f.read(12)
                if len(data_chunk)<12:
                    print(f"警告: サイズ/オフセット読み取り中にEOF ({filename})。"); return entries

                try:
                    file_size, unknown_param, file_offset = struct.unpack('<III', data_chunk)
                    entries.append({'filename_ras': filename, 'size': file_size, 'offset': file_offset, 'unknown_param': unknown_param})
                except struct.error as e:
                    print(f"エラー: サイズ/オフセット解析失敗 ({filename}): {e}"); return entries # エラー時は解析中断

    except FileNotFoundError: print(f"エラー: メタデータファイルが見つかりません: {metadata_path}"); return None
    except Exception as e: print(f"エラー: メタデータ解析中に予期せぬエラー ({metadata_path}): {e}"); return None

# --- メイン処理関数 ---
def process_files(metadata_path, archive_path, output_dir):
    """指定されたメタデータとアーカイブファイルからテクスチャを抽出します。"""
    print("="*50)
    print(f"メタデータファイル: {metadata_path}")
    print(f"アーカイブファイル: {archive_path}")
    print(f"出力ディレクトリ:   {output_dir}")
    print("-" * 50)

    # ファイル存在チェック
    if not os.path.isfile(metadata_path):
        print(f"エラー: メタデータファイルが見つかりません: {metadata_path}")
        return 0, 1 # extracted_count, error_count
    if not os.path.isfile(archive_path):
        print(f"エラー: アーカイブファイルが見つかりません: {archive_path}")
        return 0, 1 # extracted_count, error_count

    metadata_entries = parse_metadata(metadata_path)
    if metadata_entries is None or not metadata_entries:
        print("メタデータ解析失敗またはエントリなし。", file=sys.stderr)
        return 0, 1 # extracted_count, error_count
    print(f"-> {len(metadata_entries)} 件のメタデータエントリを検出。")

    print(f"\nアーカイブ '{os.path.basename(archive_path)}' からテクスチャを抽出中...")
    extracted_count = 0; error_count = 0; processed_files = 0
    unknown_header_formats_log = defaultdict(list) # Keep this per-archive pair

    try:
        with open(archive_path, 'rb') as archive_file:
            total_entries = len(metadata_entries)
            for i, entry in enumerate(metadata_entries):
                processed_files += 1
                filename_ras = entry['filename_ras']; offset = entry['offset']; size = entry['size']

                if processed_files % 100 == 0 or processed_files == total_entries:
                    print(f"\n--- 処理中 ({os.path.basename(archive_path)}): {processed_files}/{total_entries} ---")
                print(f"[{processed_files}/{total_entries}] ファイル: {filename_ras} (Offset:{offset}, Size:{size})")

                if size <= EXPECTED_HEADER_SIZE:
                    print(f"警告: サイズ({size})が小さすぎるためスキップ。"); error_count += 1; continue

                try:
                    archive_file.seek(offset); texture_data_chunk = archive_file.read(size)
                    if len(texture_data_chunk) < size:
                        print(f"警告: データ読み込み不足 ({len(texture_data_chunk)}/{size})。スキップ。"); error_count += 1; continue

                    header_bytes = texture_data_chunk[:EXPECTED_HEADER_SIZE]; pixel_data_bytes = texture_data_chunk[EXPECTED_HEADER_SIZE:]

                    try:
                        width=struct.unpack('<I',header_bytes[HEADER_WIDTH_OFFSET:HEADER_WIDTH_OFFSET+4])[0]
                        height=struct.unpack('<I',header_bytes[HEADER_HEIGHT_OFFSET:HEADER_HEIGHT_OFFSET+4])[0]
                        assert 0<width<8192 and 0<height<8192
                    except:
                        print(f"エラー: ヘッダから有効な幅/高さを読めません。スキップ。"); error_count += 1; continue

                    if len(header_bytes) < HEADER_FORMAT_FLAG_OFFSET + HEADER_FORMAT_FLAG_LEN:
                        print(f"エラー: ヘッダサイズ不足でフォーマットフラグ読めず。スキップ。"); error_count += 1; continue

                    format_flag_bytes = header_bytes[HEADER_FORMAT_FLAG_OFFSET : HEADER_FORMAT_FLAG_OFFSET + HEADER_FORMAT_FLAG_LEN];
                    # print(f"  ヘッダフォーマットフラグ: {format_flag_bytes.hex()}") # Uncomment for debugging

                    img_out = None; detected_format_str = "Unknown"; output_ext = ".png"
                    if format_flag_bytes == FORMAT_FLAG_RGB565:
                        detected_format_str = "RGB565"; # print(f" -> フォーマット: {detected_format_str}")
                        try: img_array=convert_rgb565_to_rgb888(pixel_data_bytes,width,height); img_out=Image.fromarray(img_array,'RGB')
                        except Exception as e: print(f"   -> RGB565変換エラー: {e}"); error_count += 1; continue
                    elif format_flag_bytes == FORMAT_FLAG_ARGB4444:
                        detected_format_str = "ARGB4444"; # print(f" -> フォーマット: {detected_format_str}")
                        try: img_array=convert_argb4444_to_rgba8888(pixel_data_bytes,width,height); img_out=Image.fromarray(img_array,'RGBA')
                        except Exception as e: print(f"   -> ARGB4444変換エラー: {e}"); error_count += 1; continue
                    else:
                        format_hex = format_flag_bytes.hex(); unknown_header_formats_log[format_hex].append(filename_ras)
                        print(f"警告: 未知のヘッダーフォーマットフラグ ({format_hex})。スキップ。"); error_count += 1; continue

                    if img_out:
                        output_basename = os.path.splitext(filename_ras)[0]; output_path = os.path.join(output_dir, f"{output_basename}{output_ext}")
                        try:
                            img_out.save(output_path); print(f" -> 保存成功: {output_path} ({detected_format_str})"); extracted_count += 1
                        except Exception as save_e: print(f"エラー: ファイル保存失敗 '{output_path}': {save_e}"); error_count += 1
                    else: print(f"エラー: イメージ生成失敗 ({filename_ras}, {detected_format_str})。"); error_count += 1

                except Exception as e: print(f"予期せぬエラー ({filename_ras}): {e}"); error_count += 1

    except FileNotFoundError: # Should be caught earlier, but keep for safety
        print(f"エラー: アーカイブファイルが見つかりません: {archive_path}", file=sys.stderr); error_count += total_entries - processed_files
        return extracted_count, error_count
    except Exception as e:
        print(f"エラー: アーカイブ処理中にエラー: {e}", file=sys.stderr); error_count += total_entries - processed_files
        return extracted_count, error_count

    # --- Display unknown formats for this pair ---
    if unknown_header_formats_log:
        print(f"\n--- 未知のヘッダーフォーマットフラグ ログ ({os.path.basename(archive_path)}) ---")
        sorted_unknown = sorted(unknown_header_formats_log.items(), key=lambda item: len(item[1]), reverse=True)
        for hex_str, filenames in sorted_unknown:
            print(f"フラグ [{HEADER_FORMAT_FLAG_OFFSET}:{HEADER_FORMAT_FLAG_OFFSET+HEADER_FORMAT_FLAG_LEN}]: {hex_str} ({len(filenames)} 回)")
            display_limit = 5; filenames_display = filenames[:display_limit]; ellipsis = "..." if len(filenames) > display_limit else ""
            print(f"  該当ファイル例: {', '.join(filenames_display)}{ellipsis}")
        print("-----------------------------------------------------")
    else:
        print(f"\n未知のヘッダーフォーマットフラグは検出されませんでした ({os.path.basename(archive_path)})。")

    print(f"\n--- 処理結果 ({os.path.basename(archive_path)}) ---")
    print(f"処理完了エントリ: {processed_files} / {total_entries}")
    print(f"画像保存成功: {extracted_count} ファイル")
    print(f"エラーまたはスキップ: {error_count} エントリ")

    return extracted_count, error_count


# --- メイン実行ブロック ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TextureStream_*.bin アーカイブからテクスチャを抽出し、TextureInfo_*.bin メタデータに基づいてPNGファイルとして保存します。')
    parser.add_argument('metadata_pattern', help='メタデータファイル名のパターン (例: "TexInfo_*.bin")')
    parser.add_argument('archive_pattern', help='アーカイブファイル名のパターン (例: "Tex_*.bin")')
    parser.add_argument('output_dir', help='抽出したPNGファイルを保存するディレクトリ')

    args = parser.parse_args()

    metadata_pattern = args.metadata_pattern
    archive_pattern = args.archive_pattern
    output_dir = args.output_dir

    print("="*60); print(" Texture Extraction Script (Command-Line)"); print("="*60)
    print(f"メタデータパターン: {metadata_pattern}")
    print(f"アーカイブパターン: {archive_pattern}")
    print(f"出力ディレクトリ:   {output_dir}")
    print("-" * 60)

    # 出力ディレクトリを作成 (存在しない場合)
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"出力ディレクトリ '{output_dir}' の準備完了。")
    except OSError as e:
        sys.exit(f"エラー: 出力ディレクトリを作成できません: {output_dir} - {e}")

    # ファイルパターンに一致するファイルを探す
    metadata_files = sorted(glob.glob(metadata_pattern))
    archive_files_dict = {os.path.basename(f): f for f in glob.glob(archive_pattern)} # Map basename to full path

    if not metadata_files:
        sys.exit(f"エラー: メタデータパターンに一致するファイルが見つかりません: {metadata_pattern}")
    if not archive_files_dict:
        sys.exit(f"エラー: アーカイブパターンに一致するファイルが見つかりません: {archive_pattern}")

    print(f"\n検出されたメタデータファイル ({len(metadata_files)} 件):")
    for meta_file in metadata_files:
        print(f" - {meta_file}")

    total_extracted = 0
    total_errors = 0
    processed_pairs = 0

    # メタデータファイルごとに対応するアーカイブファイルを探して処理
    for metadata_path in metadata_files:
        # 対応するアーカイブファイル名を作成 (例: TexInfo_ABC.bin -> Tex_ABC.bin)
        meta_basename = os.path.basename(metadata_path)
        if meta_basename.startswith("TexInfo_"):
            archive_basename = "Tex_" + meta_basename[len("TexInfo_"):]
        else:
            # Simple fallback: try replacing Info with Stream or just use the pattern base name?
            # This might need adjustment based on actual naming conventions.
            # For now, we'll just warn if the expected pattern isn't found.
            print(f"警告: メタデータファイル名 '{meta_basename}' が期待される 'TexInfo_*' 形式ではありません。対応するアーカイブファイルを見つけられない可能性があります。")
            archive_basename = None # Flag that we couldn't determine the corresponding archive

        corresponding_archive_path = archive_files_dict.get(archive_basename) if archive_basename else None

        if corresponding_archive_path:
            print(f"\n処理ペア:")
            print(f"  メタデータ: {metadata_path}")
            print(f"  アーカイブ: {corresponding_archive_path}")
            extracted, errors = process_files(metadata_path, corresponding_archive_path, output_dir)
            total_extracted += extracted
            total_errors += errors
            processed_pairs += 1
        else:
            print(f"\n警告: メタデータファイル '{metadata_path}' に対応するアーカイブファイルが見つかりません (ファイル名 '{archive_basename}' を探しました)。スキップします。")
            # Increment error count based on potential entries? Difficult without parsing metadata first.
            # Let's just count this as one "pair" error.
            total_errors += 1

    # --- 最終結果表示 ---
    print(f"\n{'='*60}")
    print(f" 全体の最終結果")
    print(f"{'='*60}")
    print(f"処理したファイルペア数: {processed_pairs}")
    print(f"合計画像保存成功: {total_extracted} ファイル")
    print(f"合計エラーまたはスキップ: {total_errors} (ファイルペアのエラー含む)")
    print(f"出力先ディレクトリ: {output_dir}")

    print("\nスクリプト終了。")