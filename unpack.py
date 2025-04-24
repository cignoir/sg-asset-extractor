import sys
import os
import struct
import argparse # 引数解析をより分かりやすくするために使用

# C++ の InfoData 構造体に対応する情報
# < : リトルエンディアン
# 32s: 32バイトのバイト列 (文字列)
# L: 符号なし long (C言語の unsigned long、通常4バイトと仮定)
INFO_DATA_FORMAT = '<32sLLL'
INFO_DATA_SIZE = struct.calcsize(INFO_DATA_FORMAT) # フォーマットからサイズを計算 (44バイトになるはず)

def main(info_file_path, data_file_path, output_dir):
    """
    バイナリファイルを展開するメイン関数
    """
    # 出力ディレクトリが存在しない場合は作成
    # exist_ok=True で、ディレクトリが既に存在してもエラーにならない
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 情報ファイルとデータファイルをバイナリ読み込みモードでオープン
        with open(info_file_path, 'rb') as f_info, \
             open(data_file_path, 'rb') as f_data:

            while True:
                # 情報ファイルから構造体1つ分のデータを読み込む
                info_data_packed = f_info.read(INFO_DATA_SIZE)

                # ファイルの終端に達したらループを抜ける
                if not info_data_packed:
                    break

                # 読み込んだデータが構造体のサイズより小さい場合 (ファイルの破損など)
                if len(info_data_packed) < INFO_DATA_SIZE:
                    print("Warning: Incomplete data read from info file. Stopping.", file=sys.stderr)
                    break

                # バイナリデータをアンパック
                # fileName_bytes, fileSize, fileSize2, startPos が得られる
                try:
                    unpacked_data = struct.unpack(INFO_DATA_FORMAT, info_data_packed)
                except struct.error as e:
                    print(f"Error unpacking data: {e}", file=sys.stderr)
                    continue # エラーが発生したら次のレコードへ

                file_name_bytes = unpacked_data[0]
                file_size = unpacked_data[1] # fileSize2 (unpacked_data[2]) は未使用
                start_pos = unpacked_data[3]

                # バイト列のファイル名をデコードし、NULLバイト(\x00)以降を除去
                try:
                    # 一般的なエンコーディングを試す。不明な場合は 'ignore' でエラーを回避
                    file_name = file_name_bytes.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                except UnicodeDecodeError as e:
                     print(f"Warning: Could not decode filename bytes: {file_name_bytes}. Error: {e}", file=sys.stderr)
                     # デコードできない場合は適当な名前をつけるかスキップするなどの対応も可能
                     file_name = f"undecodable_{start_pos}.bin" # 例: 開始位置を名前に使う

                # ファイル名が空の場合はスキップ (NULLバイトのみのファイル名など)
                if not file_name:
                    print(f"Warning: Skipping entry with empty filename at position {f_info.tell() - INFO_DATA_SIZE}", file=sys.stderr)
                    continue

                print(f"Extracting: {file_name} (Size: {file_size}, Pos: {start_pos})")

                # データファイル内の該当位置に移動
                try:
                    f_data.seek(start_pos)
                except OSError as e:
                     print(f"Error seeking in data file to position {start_pos}: {e}", file=sys.stderr)
                     continue # 次のレコードへ

                # ファイルサイズ分のデータを読み込む
                try:
                    file_content = f_data.read(file_size)
                    if len(file_content) < file_size:
                        print(f"Warning: Expected {file_size} bytes for {file_name}, but got {len(file_content)} bytes.", file=sys.stderr)
                        # データが足りなくても処理を続行する場合
                        if not file_content:
                             print(f"Warning: No data read for {file_name}. Skipping file.", file=sys.stderr)
                             continue

                except OSError as e:
                    print(f"Error reading data for {file_name}: {e}", file=sys.stderr)
                    continue # 次のレコードへ

                # 出力ファイルパスを構築
                output_file_path = os.path.join(output_dir, file_name)

                # 出力ファイルをバイナリ書き込みモードでオープンし、データを書き込む
                try:
                    with open(output_file_path, 'wb') as f_out:
                        f_out.write(file_content)
                except OSError as e:
                    print(f"Error writing file {output_file_path}: {e}", file=sys.stderr)
                except Exception as e:
                    print(f"An unexpected error occurred while writing {output_file_path}: {e}", file=sys.stderr)


    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error accessing file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print('Unpacking completed.')

if __name__ == '__main__':
    # コマンドライン引数のパーサーを設定
    parser = argparse.ArgumentParser(description='Unpack files from binary archives based on an info file.')
    parser.add_argument('info_file', help='Path to the information file (*Info.bin)')
    parser.add_argument('data_file', help='Path to the data file (*.bin)')
    parser.add_argument('output_dir', help='Directory to unpack files into')

    # 引数を解析
    args = parser.parse_args()

    # メイン関数を実行
    main(args.info_file, args.data_file, args.output_dir)