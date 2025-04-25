# -*- coding: utf-8 -*-
# split_text_file.py

import sys
import os
import locale
import argparse
import platform # OSを判定するためにインポート

# 分割サイズの上限 (バイト単位)
# 100MB = 100 * 1024 * 1024 bytes
MAX_SIZE = 100 * 1000 * 1000
# テスト用に小さいサイズにする場合 (例: 1MB)
# MAX_SIZE = 1 * 1024 * 1024

def detect_encoding(filepath):
    """
    ファイルのエンコーディングを推定する関数。
    一般的なエンコーディングを試す。
    """
    # 試すエンコーディングのリスト (優先順位順)
    encodings_to_try = [
        locale.getpreferredencoding(False), # システムのデフォルト
        'utf-8',
        'cp932',  # Shift_JIS (Windows日本語環境)
        'euc-jp',
        'iso2022-jp' # JIS
    ]
    # BOM付きUTF-8のチェック
    try:
        with open(filepath, 'rb') as f:
            bom = f.read(3)
            if bom.startswith(b'\xef\xbb\xbf'):
                print("BOM付きUTF-8を検出しました。")
                return 'utf-8-sig' # BOMを処理するUTF-8
    except Exception:
        pass # ファイル読み込みエラーなどは後続で処理

    # ファイルの先頭を読み込んでエンコーディングを試す
    try:
        with open(filepath, 'rb') as fb:
            sample = fb.read(4096) # 先頭4KBを読み込む
            if not sample: # 空ファイルの場合
                 print("警告: 空ファイルです。")
                 # デフォルトエンコーディングを返すか、Noneを返すか選択
                 return locale.getpreferredencoding(False) or 'utf-8'

            for enc in encodings_to_try:
                if enc is None: continue
                try:
                    sample.decode(enc)
                    print(f"ファイルエンコーディングを '{enc}' と推定しました。")
                    return enc
                except (UnicodeDecodeError, LookupError, TypeError):
                    continue # デコード失敗、次のエンコーディングへ
    except Exception as e:
        print(f"エンコーディング判別中にエラーが発生しました: {e}")
        # エラーが発生した場合でも、フォールバックを試みる

    # フォールバックとしてUTF-8を試す
    print("警告: エンコーディングの自動判別に失敗しました。デフォルトとして 'utf-8' を使用します。")
    return 'utf-8'

def split_file(filepath, max_size):
    """ファイルを指定サイズ以下に厳密に分割する関数 (Windows改行コード考慮)"""
    # ファイルの存在と種類を確認
    if not os.path.exists(filepath):
        print(f"エラー: ファイルが見つかりません: {filepath}")
        return
    if not os.path.isfile(filepath):
        print(f"エラー: 通常のファイルではありません: {filepath}")
        return

    try:
        # 元ファイルのディレクトリ、ベース名、拡張子を取得
        file_dir = os.path.dirname(filepath)
        base_name, ext = os.path.splitext(os.path.basename(filepath))

        # ファイルエンコーディングを推定
        infile_encoding = detect_encoding(filepath)
        if infile_encoding is None:
             print("エラー: ファイルエンコーディングを決定できませんでした。処理を中断します。")
             return

        # --- ファイル分割処理 ---
        part_num = 1
        current_size = 0
        outfile = None
        output_filepath = "" # finally節やエラー表示用に保持
        is_windows = platform.system() == "Windows" # Windowsかどうかを判定

        print(f"ファイルを分割中: {filepath} (エンコーディング: {infile_encoding})")

        # 元ファイルをテキストモードで開く
        try:
            # newline='' を指定して、読み込み時の改行コード変換を抑制
            with open(filepath, 'r', encoding=infile_encoding, errors='ignore', newline='') as infile:
                while True:
                    line = infile.readline()
                    if not line:
                        break # ファイル終端

                    # 行のバイト数を取得
                    try:
                        write_encoding = 'utf-8' if infile_encoding == 'utf-8-sig' else infile_encoding
                        encoded_line = line.encode(write_encoding)
                        line_bytes = len(encoded_line)

                        # --- Windows改行コード (\r\n) の考慮 ---
                        # Pythonのテキストモード書き込みはWindowsで \n を \r\n に変換する
                        # readline() は \n または \r\n で終わるため、\n で終わる場合に
                        # Windows環境では書き込み時に1バイト追加される可能性がある
                        if is_windows and line.endswith('\n') and not line.endswith('\r\n'):
                             # マルチバイト文字の途中で改行されるケースは稀だが考慮は難しい
                             # 基本的に行末の\nが\r\nになる分の1バイトを追加計算
                             line_bytes += 1
                             # print(f"Debug: Adding 1 byte for Windows newline conversion. Original bytes: {len(encoded_line)}, Adjusted: {line_bytes}")


                    except Exception as e:
                        print(f"警告: 行 '{line[:50]}...' のエンコード中にエラー。スキップします。エラー: {e}")
                        continue

                    # --- 厳密なサイズチェック ---
                    # 1. この行自体が大きすぎるかチェック
                    if line_bytes > max_size:
                        print(f"警告: 1行 ({line_bytes / (1024*1024):.2f} MB) が最大サイズ ({max_size / (1024*1024):.2f} MB) を超過。この行はスキップされます。")
                        if outfile:
                            outfile.close()
                            print(f"  -> (前のファイルを閉じる) 保存完了: {os.path.basename(output_filepath)} ({current_size / (1024*1024):.2f} MB)")
                            outfile = None
                            current_size = 0
                        continue

                    # 2. 新しいファイルを開始する必要があるかチェック
                    start_new_file = (outfile is None) or (current_size + line_bytes > max_size)

                    if start_new_file:
                        if outfile:
                            outfile.close()
                            print(f"  -> 保存完了: {os.path.basename(output_filepath)} ({current_size / (1024*1024):.2f} MB)")
                            outfile = None

                        output_filename = f"{base_name}_part{part_num}{ext}"
                        output_filepath = os.path.join(file_dir, output_filename)
                        try:
                            # 書き込み時も newline='' を指定しない (Pythonに適切な改行コード処理を任せる)
                            outfile = open(output_filepath, 'w', encoding=write_encoding, errors='ignore')
                            print(f"分割ファイル {part_num} を作成中: {os.path.basename(output_filepath)}...")
                            current_size = 0
                            part_num += 1
                        except Exception as e:
                            print(f"エラー: 分割ファイル '{output_filepath}' の作成に失敗しました: {e}")
                            if outfile: outfile.close()
                            return

                    # 3. 行を現在のファイルに書き込む
                    if outfile:
                        try:
                            outfile.write(line)
                            current_size += line_bytes # 事前に計算したバイト数を加算
                        except Exception as e:
                            print(f"エラー: ファイル '{output_filepath}' への書き込み中にエラー: {e}")
                            outfile.close()
                            return
                    else:
                        print("エラー: 書き込み対象のファイルが開かれていません。処理を中断します。")
                        return

            # ループ終了後、最後に開いていたファイルを閉じる
            if outfile and not outfile.closed:
                outfile.close()
                print(f"  -> 保存完了: {os.path.basename(output_filepath)} ({current_size / (1024*1024):.2f} MB)")

            print("-" * 30)
            print("ファイルの分割が正常に完了しました。")
            print("-" * 30)

        except FileNotFoundError:
            print(f"エラー: 指定されたファイルが見つかりません: {filepath}")
        except IOError as e:
            print(f"エラー: ファイルI/Oエラーが発生しました: {e}")
        except UnicodeDecodeError as e:
            print(f"エラー: ファイルのデコードに失敗しました。エンコーディング '{infile_encoding}' が間違っている可能性があります。エラー: {e}")
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {e}")

    finally:
        if outfile and not outfile.closed:
            print("警告: finallyブロックでファイルを閉じます。")
            outfile.close()


if __name__ == "__main__":
    # コマンドライン引数のパーサーを設定
    parser = argparse.ArgumentParser(description="テキストファイルを指定サイズ以下に厳密に分割します。")
    parser.add_argument("filepath", help="分割するテキストファイルのパス")
    parser.add_argument("-s", "--size", type=int, default=MAX_SIZE,
                        help=f"分割サイズの上限（バイト単位）。デフォルト: {MAX_SIZE} ({MAX_SIZE//(1024*1024)}MB)")
    parser.add_argument("--wait", action='store_true',
                        help="処理完了後にキー入力を待つ (コンテキストメニューからの実行時は通常不要)")

    args = parser.parse_args()

    # ファイル分割関数を呼び出し
    split_file(args.filepath, args.size)

    # --wait オプションが指定された場合、または引数なしで直接実行された場合のみ待機
    if args.wait or len(sys.argv) == 1:
        try:
            input("何かキーを押して終了します...")
        except EOFError: # パイプ経由などで入力がない場合
            pass
