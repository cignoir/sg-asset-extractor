#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import subprocess
from pathlib import Path

def analyze_ame_files(directory, output_file=None):
    """
    指定されたディレクトリ内のすべての.ameファイルを解析し、
    結果を標準出力またはファイルに出力します（parse_binary.pyを使用）。
    """
    print(f"ディレクトリ {directory} 内の.ameファイルを解析します...")

    # ディレクトリ内のすべての.ameファイルを取得
    ame_files = list(Path(directory).glob('*.ame'))
    print(f"{len(ame_files)}個の.ameファイルが見つかりました。")

    if not ame_files:
        print(f"エラー: {directory} 内に.ameファイルが見つかりません。", file=sys.stderr)
        sys.exit(1)

    # 出力ファイルが指定されている場合、既存の内容をクリア（TSV追記のため）
    if output_file:
        output_path = os.path.abspath(output_file)
        try:
            # TSVヘッダーを書き込むか、ファイルをクリア
            # ここではシンプルにファイルをクリアし、parse_binary.pyにヘッダー出力は任せない
            with open(output_path, 'w') as f:
                pass # ファイルを空にする
            print(f"結果を {output_path} に保存します...")
        except Exception as e:
            print(f"エラー: 出力ファイル {output_path} の準備中にエラーが発生しました: {e}", file=sys.stderr)
            sys.exit(1)

    # 各ファイルを解析
    for ame_file in ame_files:
        try:
            # parse_binary.py をサブプロセスとして実行
            command = [
                sys.executable, # 現在のPythonインタープリタを使用
                'parse_binary.py',
                str(ame_file),
                '--tsv' # 常にTSVモードで実行
            ]
            if output_file:
                command.extend(['-o', output_path]) # 出力ファイルを指定

            # サブプロセスを実行し、標準出力をキャプチャ
            # 出力ファイルが指定されている場合は、parse_binary.pyが直接ファイルに書き込むため、
            # analyze_ame_files.py側では標準出力をキャプチャする必要はない
            if output_file:
                 result = subprocess.run(command, check=True, capture_output=False)
            else:
                 result = subprocess.run(command, check=True, capture_output=True, text=True)
                 # 標準出力に結果を表示
                 print(result.stdout.strip())


        except subprocess.CalledProcessError as e:
            print(f"エラー: {ame_file} の解析中にエラーが発生しました（parse_binary.py実行エラー）:", file=sys.stderr)
            print(f"コマンド: {' '.join(e.cmd)}", file=sys.stderr)
            print(f"標準エラー出力:\n{e.stderr}", file=sys.stderr)
        except FileNotFoundError:
             print(f"エラー: parse_binary.py が見つかりません。スクリプトと同じディレクトリに存在することを確認してください。", file=sys.stderr)
             sys.exit(1)
        except Exception as e:
            print(f"エラー: {ame_file} の解析中に予期せぬエラーが発生しました: {e}", file=sys.stderr)

    if output_file:
        print(f"すべてのファイルの解析結果を {output_path} に保存しました。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='.ameファイルを解析し、結果を出力します（parse_binary.pyを使用）。')
    parser.add_argument('directory', help='解析する.ameファイルが含まれるディレクトリのパス')
    parser.add_argument('-o', '--output', help='出力先ファイルのパス（指定しない場合は標準出力）')

    args = parser.parse_args()

    analyze_ame_files(args.directory, args.output)
