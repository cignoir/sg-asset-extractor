import os
import struct
import argparse

# アンパック時に使用した構造体フォーマットと同じものを定義
# < : リトルエンディアン
# 32s: 32バイトのバイト列 (文字列)
# L: 符号なし long (C言語の unsigned long、通常4バイトと仮定)
INFO_DATA_FORMAT = '<32sLLL'
INFO_DATA_SIZE = struct.calcsize(INFO_DATA_FORMAT)

# ファイル名を32バイトに調整（パディング/切り詰め）する関数
def adjust_filename(filename_str, encoding='utf-8'):
    """ファイル名を指定されたエンコーディングでバイト列に変換し、32バイトに調整する"""
    try:
        filename_bytes = filename_str.encode(encoding)
    except UnicodeEncodeError as e:
        print(f"Warning: Could not encode filename '{filename_str}' using {encoding}: {e}. Skipping file.", file=sys.stderr)
        return None # エンコード失敗

    # 32バイトより長い場合は切り詰める
    if len(filename_bytes) > 32:
        print(f"Warning: Filename '{filename_str}' is longer than 32 bytes after encoding. It will be truncated.", file=sys.stderr)
        filename_bytes = filename_bytes[:32]
    # 32バイトより短い場合はNULLバイト(\x00)でパディングする
    else:
        filename_bytes = filename_bytes.ljust(32, b'\x00')

    return filename_bytes

def main(input_dir, info_file_path, data_file_path, encoding='utf-8'):
    """
    フォルダ内のファイルを Info ファイルと Data ファイルにパックするメイン関数
    """
    print(f"--- Starting Packing ---")
    print(f"Input Directory: {input_dir}")
    print(f"Output Info File: {info_file_path}")
    print(f"Output Data File: {data_file_path}")
    print(f"Filename Encoding: {encoding}")
    print("-" * 20)

    # 入力ディレクトリが存在するか確認
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' not found or is not a directory.", file=sys.stderr)
        sys.exit(1)

    current_data_pos = 0
    file_count = 0
    total_size = 0

    try:
        # 出力ファイルをバイナリ書き込みモードでオープン
        with open(info_file_path, 'wb') as f_info, \
             open(data_file_path, 'wb') as f_data:

            # 入力ディレクトリ直下のファイルのみを処理 (サブディレクトリは無視)
            for item_name in sorted(os.listdir(input_dir)): # ファイル順序を安定させるためソート
                item_path = os.path.join(input_dir, item_name)

                # ファイルかどうかをチェック
                if os.path.isfile(item_path):
                    file_count += 1
                    print(f"\nProcessing file {file_count}: {item_name}")

                    # ファイル名を32バイトに調整
                    filename_adjusted = adjust_filename(item_name, encoding)
                    if filename_adjusted is None: # エンコード失敗などでスキップ
                        continue

                    # ファイルサイズを取得
                    try:
                        file_size = os.path.getsize(item_path)
                        print(f"Size: {file_size} bytes")
                    except OSError as e:
                        print(f"Error: Could not get size of file '{item_path}': {e}", file=sys.stderr)
                        continue # サイズ取得失敗ならスキップ

                    # メタデータを作成 (fileSize2 にも fileSize を入れる)
                    start_pos = current_data_pos
                    print(f"Start Position in data file: {start_pos}")

                    # struct.pack でバイナリデータに変換
                    try:
                        info_data_packed = struct.pack(INFO_DATA_FORMAT, filename_adjusted, file_size, file_size, start_pos)
                    except struct.error as e:
                         print(f"Error: Failed to pack metadata for '{item_name}': {e}", file=sys.stderr)
                         continue # パック失敗ならスキップ

                    # Info ファイルにメタデータを書き込む
                    f_info.write(info_data_packed)
                    print(f"Wrote metadata to {os.path.basename(info_file_path)}")

                    # Data ファイルにファイルの内容を書き込む
                    try:
                        with open(item_path, 'rb') as f_asset:
                            # ファイルの内容を読み込んで書き込む (大きなファイルも扱えるように)
                            while True:
                                chunk = f_asset.read(8192) # 8KBずつ読み込む
                                if not chunk:
                                    break
                                f_data.write(chunk)
                        print(f"Wrote {file_size} bytes to {os.path.basename(data_file_path)}")

                        # 次のファイルの開始位置を更新
                        current_data_pos += file_size
                        total_size += file_size

                    except IOError as e:
                        print(f"Error: Could not read file '{item_path}' or write to data file: {e}", file=sys.stderr)
                        # ここで処理を中断するか、エラーが発生したファイルをスキップするか選択
                        # 今回はエラーを出力して続行するが、Info/Dataファイルの一貫性が崩れる可能性あり
                        # 厳密には、書き込み失敗時にInfoファイルに追加したレコードを削除するなどの処理が必要
                        continue

                else:
                    print(f"Skipping non-file item: {item_name}")


    except IOError as e:
        print(f"Error: Could not open output files '{info_file_path}' or '{data_file_path}' for writing: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n--- Packing Summary ---")
    print(f"Total files processed: {file_count}")
    print(f"Total data size packed: {total_size} bytes")
    print(f"Output Info file: {info_file_path}")
    print(f"Output Data file: {data_file_path}")
    print('--- Packing process finished. ---')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pack files from a directory into an Info file and a Data file.')
    parser.add_argument('input_dir', help='Directory containing the assets to pack.')
    parser.add_argument('output_info', help='Path for the output information file (e.g., ClumpInfo_packed.bin)')
    parser.add_argument('output_data', help='Path for the output data file (e.g., Clump_packed.bin)')
    parser.add_argument('--encoding', default='utf-8', help='Encoding to use for filenames (e.g., utf-8, shift_jis). Default: utf-8')

    args = parser.parse_args()
    main(args.input_dir, args.output_info, args.output_data, args.encoding)