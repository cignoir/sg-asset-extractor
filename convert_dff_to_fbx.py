# Blenderバッチ実行スクリプト
# -*- coding: utf-8 -*-
# このスクリプトはPythonで直接実行できます。
# Blenderをバックグラウンドで起動し、DFFからFBXへの変換を実行します。
# 使用法: python convert_dff_to_fbx.py <blender_exe_path> <input_dff_dir> <output_fbx_dir>

import subprocess
import os
import sys
import platform
import argparse # コマンドライン引数処理のために追加

# --- 設定 (一部は引数で上書きされる) ---
# このスクリプトファイルの絶対パスを取得
CURRENT_SCRIPT_PATH = os.path.abspath(__file__)
# Blenderで有効にする必要のあるアドオン名
REQUIRED_ADDON = "DragonFF"
# Blender内部のスクリプトに渡す追加オプション (例: Maya形式を指定)
# 必要に応じてコマンドライン引数に追加することも検討できます
SCRIPT_OPTIONS = ["--maya"]
# ---------------------

def run_blender_script(blender_exe, script_path, addon, script_args):
    """
    Blenderをバックグラウンドで起動し、Pythonスクリプトを実行します。

    引数:
        blender_exe (str): Blender実行ファイルのパス。
        script_path (str): Blenderによって実行されるPythonスクリプトのパス。
        addon (str): 有効にするBlenderアドオンの名前。
        script_args (list): Blender内部のPythonスクリプトに渡す引数のリスト。
                          最初の2つは input_dir と output_dir である必要があります。
    """
    # Blender実行ファイルが存在するか確認
    if not os.path.isfile(blender_exe):
        print(f"エラー: 指定されたパスにBlender実行ファイルが見つかりません:")
        print(f"       '{blender_exe}'")
        sys.exit(1) # Blenderのパスが不正な場合はスクリプトを終了

    # Blenderのコマンドライン引数を構築
    command = [
        blender_exe,
        "--background",      # UIなしでBlenderを実行
        "--addons", addon,   # 指定されたアドオンを有効化
        "--python", script_path, # Blenderが実行するスクリプトを指定
        "--"                 # Pythonスクリプト向けの引数の区切り
    ]
    command.extend(script_args) # スクリプト用の引数を追加 (input_dir, output_dir, SCRIPT_OPTIONS...)

    print("-" * 60)
    print("以下のコマンドでBlenderを起動しようとしています:")
    # コマンドを明確に表示（スペースを含む引数は引用符で囲む）
    print(" ".join(f'"{arg}"' if " " in arg else arg for arg in command))
    print("-" * 60)

    try:
        # Blenderコマンドを実行
        process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')

        # Blenderスクリプト実行からの出力を表示
        print("\n--- Blender スクリプト出力 (標準出力) ---")
        print(process.stdout if process.stdout else "(標準出力なし)")
        print("------------------------------------")
        if process.stderr:
            print("\n--- Blender スクリプト出力 (標準エラー) ---")
            print(process.stderr)
            print("------------------------------------")

        print("\nBlenderプロセスは正常に終了しました。")

    except FileNotFoundError:
        print(f"エラー: Blenderの起動に失敗しました。コマンド '{blender_exe}' が見つかりませんでした。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"エラー: Blenderプロセスが終了コード {e.returncode} で失敗しました。")
        print("\n--- Blender スクリプト出力 (標準出力) ---")
        print(e.stdout if e.stdout else "(標準出力なし)")
        print("------------------------------------")
        print("\n--- Blender スクリプト出力 (標準エラー) ---")
        print(e.stderr if e.stderr else "(標準エラー出力なし)")
        print("------------------------------------")
        print("エラーの詳細については、上記のBlender出力を確認してください。")
        sys.exit(1)
    except Exception as e:
        print(f"Blenderの実行中に予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# --- メイン実行ロジック ---
if __name__ == "__main__":
    try:
        import bpy
        # --- Blender内部で実行されるコードパス ---
        print("\n>>> Blender環境内で実行中 <<<")

        import glob
        import math
        from mathutils import Matrix

        def batch_convert_dff_to_fbx_internal():
            """
            Blender内で実行される実際のDFFからFBXへの変換ロジック。
            '--' の後に渡された引数を読み取ります。
            """
            print("   内部DFFからFBXへの変換プロセスを開始...")
            # --- 1. コマンドライン引数（'--' 以降）の処理 ---
            try:
                idx = sys.argv.index("--")
                args = sys.argv[idx + 1:]
            except ValueError:
                print("   エラー: '--'以降にBlender内部スクリプト用の引数が見つかりません。")
                print("         スクリプトは input_dir と output_dir を期待しています。")
                sys.exit(1) # 必須引数がないため終了

            if len(args) < 2:
                print("   エラー: Blender内部スクリプトには少なくとも2つの引数 (input_dir, output_dir) が必要です。")
                print(f"          受け取った引数: {args}")
                sys.exit(1)

            dff_dir = args[0]
            fbx_dir = args[1]
            options = args[2:] # 追加オプション

            # Blender内部でも絶対パスを使用することを推奨（相対パスでも機能する可能性はありますが）
            dff_dir_abs = os.path.abspath(dff_dir)
            fbx_dir_abs = os.path.abspath(fbx_dir)
            # 出力ディレクトリはメインスクリプト側で作成されているはずだが、念のため確認
            os.makedirs(fbx_dir_abs, exist_ok=True)

            print("   --- 内部設定 ---")
            print(f"   入力DFFディレクトリ: {dff_dir_abs}")
            print(f"   出力FBXディレクトリ: {fbx_dir_abs}")
            print(f"   オプション: {options}")
            print("   ----------------------------")

            # --- 2. FBXエクスポート設定の定義 ---
            export_preset = "Maya Y-up" # または必要に応じて変更
            fbx_export_settings = {
                'axis_forward': 'Z',
                'axis_up': 'Y',
                'bake_space_transform': True,
                'use_selection': False,
                'apply_unit_scale': True,
                'object_types': {'MESH', 'ARMATURE'},
                'add_leaf_bones': False,
                'path_mode': 'AUTO',
            }
            print(f"   FBXエクスポートプリセットを使用: {export_preset}")

            # --- 3. DFFファイルの検索と処理 ---
            dff_pattern = os.path.join(dff_dir_abs, "*.dff")
            dff_files = glob.glob(dff_pattern)

            if not dff_files:
                print(f"   警告: '{dff_dir_abs}' に *.dff ファイルが見つかりません。")
                return # 処理するファイルがない

            print(f"   {len(dff_files)} 個の DFF ファイルが見つかりました。バッチ変換を開始します...")
            processed_count = 0
            error_count = 0

            for i, dff_path in enumerate(dff_files):
                base_name = os.path.splitext(os.path.basename(dff_path))[0]
                fbx_filename = f"{base_name}.fbx"
                fbx_path = os.path.join(fbx_dir_abs, fbx_filename)
                print(f"\n   [{i + 1}/{len(dff_files)}] 処理中: {os.path.basename(dff_path)}")
                try:
                    bpy.ops.wm.read_homefile(use_empty=True)
                    print(f"     DFFをインポート中...")
                    bpy.ops.import_scene.dff(
                        filepath=dff_path,
                        load_txd=True,
                        load_images=True,
                        connect_bones=False
                    )
                    print(f"     {len(bpy.context.scene.objects)} 個のオブジェクトをインポートしました。")
                    print(f"     FBXを '{fbx_filename}' にエクスポート中...")
                    bpy.ops.export_scene.fbx(
                        filepath=fbx_path,
                        **fbx_export_settings
                    )
                    print(f"   ✓ OK: {os.path.basename(dff_path)} -> {fbx_filename}")
                    processed_count += 1
                except Exception as e:
                    print(f"   ! エラー {os.path.basename(dff_path)} の変換中: {e}")
                    import traceback
                    traceback.print_exc()
                    error_count += 1

            # --- 4. 最終レポート（Blender内部） ---
            print("\n   --- 変換サマリー (Blender内部) ---")
            print(f"   見つかったDFFファイルの総数: {len(dff_files)}")
            print(f"   正常に変換された数: {processed_count}")
            print(f"   発生したエラー数: {error_count}")
            print("   -----------------------------------------")
            print(">>> Blender スクリプト終了 <<<")

        batch_convert_dff_to_fbx_internal()

    except ImportError:
        # --- Blender外部で実行されるコードパス ---
        print("\n>>> Blender環境外で実行中 <<<")

        # --- コマンドライン引数の解析 ---
        parser = argparse.ArgumentParser(description='Blenderを使用してDFFファイルをFBXにバッチ変換します。')
        parser.add_argument('blender_exe', help='Blender実行ファイルのパス (例: C:/Program Files/Blender Foundation/Blender 4.1/blender.exe)')
        parser.add_argument('input_dir', help='入力DFFファイルが含まれるディレクトリのパス')
        parser.add_argument('output_dir', help='出力FBXファイルを保存するディレクトリのパス')
        # オプションで SCRIPT_OPTIONS も引数化する場合はここに追加
        # parser.add_argument('--maya', action='store_true', help='Maya形式のオプションを有効にする')

        args = parser.parse_args()

        # 入力ディレクトリが存在するか確認
        if not os.path.isdir(args.input_dir):
            print(f"エラー: 入力ディレクトリが見つかりません: '{args.input_dir}'")
            sys.exit(1)

        # 出力ディレクトリを作成（存在しない場合）
        try:
            os.makedirs(args.output_dir, exist_ok=True)
            print(f"出力ディレクトリ: '{os.path.abspath(args.output_dir)}'")
        except OSError as e:
            print(f"エラー: 出力ディレクトリを作成できません: '{args.output_dir}' - {e}")
            sys.exit(1)

        # Blender内部で実行されるスクリプト用の引数を準備
        # 順番が重要: input_dir, output_dir, その他のオプション
        blender_script_arguments = [args.input_dir, args.output_dir]
        blender_script_arguments.extend(SCRIPT_OPTIONS) # 固定の追加オプションを追加

        # Blenderを起動する関数を呼び出し
        run_blender_script(
            args.blender_exe,
            CURRENT_SCRIPT_PATH, # このスクリプトのパスをBlenderに渡す
            REQUIRED_ADDON,
            blender_script_arguments
        )