import sys
import os
import argparse

def generate_hexdump(input_filename, output_filename, bytes_per_line=16, max_output_bytes=None):
    """
    バイナリファイルからヘキサダンプを生成し、テキストファイルに出力する関数

    Args:
        input_filename (str): 入力バイナリファイル名
        output_filename (str): 出力テキストファイル名
        bytes_per_line (int): 1行あたりに表示するバイト数 (デフォルト: 16)
        max_output_bytes (int | None): 出力ファイルの最大許容バイト数。Noneの場合は無制限。
    """
    total_bytes_written = 0
    limit_reached = False

    try:
        with open(input_filename, 'rb') as infile, \
             open(output_filename, 'wt', encoding='utf-8') as outfile:

            offset = 0
            while True:
                # 指定バイト数ずつ読み込み
                chunk = infile.read(bytes_per_line)
                if not chunk:
                    break # ファイルの終端に達したらループを抜ける

                # 1. オフセット部分
                offset_str = f"{offset:08x}"

                # 2. 16進数表現部分
                hex_values = []
                for i in range(bytes_per_line):
                    if i < len(chunk):
                        hex_values.append(f"{chunk[i]:02x}")
                    else:
                        hex_values.append("  ")
                hex_str = ' '.join(hex_values[:bytes_per_line//2]) + '  ' + ' '.join(hex_values[bytes_per_line//2:])

                # 3. ASCII表現部分
                ascii_chars = []
                for i in range(len(chunk)):
                    byte_val = chunk[i]
                    if 32 <= byte_val <= 126:
                        ascii_chars.append(chr(byte_val))
                    else:
                        ascii_chars.append('.')
                ascii_str = "".join(ascii_chars)

                # 行を組み立てる (改行文字も含む)
                line = f"{offset_str}  {hex_str}  |{ascii_str}|"
                line_with_newline = line + '\n'
                # この行を書き込んだ場合のバイト数を計算 (UTF-8エンコード)
                line_bytes = len(line_with_newline.encode('utf-8'))

                # --- サイズ制限チェック ---
                if max_output_bytes is not None and \
                   (total_bytes_written + line_bytes) > max_output_bytes:
                    limit_reached = True
                    print(f"\n警告: 出力ファイルサイズ制限 ({max_output_bytes / 1000000} MB) に達するため、ここで出力を停止します。", file=sys.stderr)
                    break # 制限を超えるためループを抜ける
                # --- チェックここまで ---

                # ファイルに書き込み
                outfile.write(line_with_newline)
                total_bytes_written += line_bytes

                # オフセットを更新
                offset += len(chunk)

        if limit_reached:
             print(f"ヘキサダンプを '{output_filename}' に生成しました (サイズ制限により途中で終了)。")
        else:
             print(f"ヘキサダンプを '{output_filename}' に正常に生成しました。")

    except FileNotFoundError:
        print(f"エラー: 入力ファイル '{input_filename}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"エラー: ファイルの読み書き中にエラーが発生しました ({output_filename}): {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # コマンドライン引数のパーサーを設定
    parser = argparse.ArgumentParser(
        description="バイナリファイルからヘキサダンプを生成し、'<入力ファイル名>.txt' という名前で保存します。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # mydata.bin のヘキサダンプを mydata.bin.txt に生成
  python %(prog)s mydata.bin

  # 1行あたり32バイトで出力
  python %(prog)s mydata.bin -w 32

  # 出力ファイル名を指定
  python %(prog)s mydata.bin -o dump.txt

  # 出力ファイルサイズを約 100 MB に制限
  python %(prog)s largefile.bin --limit 100
"""
    )
    # 必須引数: 入力ファイル名
    parser.add_argument("input_file", help="ヘキサダンプを生成するバイナリファイル")
    # オプション引数: 1行あたりのバイト数
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=16,
        help="出力の1行あたりに表示するバイト数 (デフォルト: 16)"
    )
    # オプション引数: 出力ファイル名
    parser.add_argument(
        "-o", "--output",
        help="出力ファイル名 (デフォルト: <入力ファイル名>.txt)"
    )
    # ★新規オプション: 出力ファイルサイズ制限 (MB単位)
    parser.add_argument(
        "--limit",
        type=float, # 小数も許可
        default=None,
        help="出力ファイルの最大サイズをMB単位で指定します。指定しない場合は無制限。 (例: 0.5, 10)"
    )

    # 引数を解析
    args = parser.parse_args()

    input_filename = args.input_file
    bytes_per_line = args.width

    # 出力ファイル名を決定
    if args.output:
        output_filename = args.output
    else:
        output_filename = input_filename + ".txt"

    # 入力ファイルが存在するかチェック
    if not os.path.exists(input_filename):
        print(f"エラー: 入力ファイル '{input_filename}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(input_filename):
         print(f"エラー: '{input_filename}' は通常のファイルではありません。", file=sys.stderr)
         sys.exit(1)

    # バイト数が正かチェック
    if bytes_per_line <= 0:
         print(f"エラー: 1行あたりのバイト数 ({bytes_per_line}) は正の整数である必要があります。", file=sys.stderr)
         sys.exit(1)

    # サイズ制限をバイト単位に変換 (1 MB = 1000 * 1000 bytes に変更)
    limit_bytes = None
    if args.limit is not None:
        if args.limit > 0:
            # Megabyte (MB) 基準で計算 (1000*1000)
            limit_bytes = int(args.limit * 1000 * 1000) # <--- この行を変更
            if limit_bytes == 0: # 非常に小さい値が指定された場合
                 print(f"エラー: 指定されたMB制限 ({args.limit} MB) が小さすぎます。", file=sys.stderr)
                 sys.exit(1)
        else:
            print(f"エラー: MB単位のサイズ制限 ({args.limit}) は正の値である必要があります。", file=sys.stderr)
            sys.exit(1)

    # ヘキサダンプ生成関数を呼び出し
    generate_hexdump(input_filename, output_filename, bytes_per_line, limit_bytes)