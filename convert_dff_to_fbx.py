# Blenderバッチ実行スクリプト
# -*- coding: utf-8 -*-
# このスクリプトはPythonで直接実行できます。
# Blenderをバックグラウンドで起動し、DFFからFBXへの変換を実行します。

import subprocess
import os
import sys
import platform
import configparser
from config_loader import load_config, get_path_from_config

# 設定読み込み
CONFIG_FILENAME = 'config.ini'
config, ini_dir = load_config(CONFIG_FILENAME)
BLENDER_EXECUTABLE_PATH = get_path_from_config(config, ini_dir, 'Paths', 'blender_executable')

# このスクリプトファイルの絶対パスを取得
CURRENT_SCRIPT_PATH = os.path.abspath(__file__)

# DFFファイルが格納されているディレクトリ (スクリプトからの相対パス or 絶対パス)
INPUT_DFF_DIR = get_path_from_config(config, ini_dir, 'DFFConversion', 'input_dir', is_dir=True)
# 変換後のFBXファイルを保存するディレクトリ (スクリプトからの相対パス or 絶対パス)
OUTPUT_FBX_DIR = get_path_from_config(config, ini_dir, 'DFFConversion', 'output_dir', is_dir=True, create_dir=True)
# Blenderで有効にする必要のあるアドオン名
REQUIRED_ADDON = "DragonFF"
# Blender内部のスクリプトに渡す追加オプション (例: Maya形式を指定)
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
    """
    # Blender実行ファイルが存在するか確認
    if not os.path.isfile(blender_exe):
        print(f"エラー: 指定されたパスにBlender実行ファイルが見つかりません:")
        print(f"       '{blender_exe}'")
        print(f"このスクリプトの'BLENDER_EXECUTABLE_PATH'変数を更新してください。")
        sys.exit(1) # Blenderのパスが不正な場合はスクリプトを終了

    # Blenderのコマンドライン引数を構築
    command = [
        blender_exe,
        "--background",      # UIなしでBlenderを実行
        "--addons", addon,   # 指定されたアドオンを有効化
        "--python", script_path, # Blenderが実行するスクリプトを指定
        "--"                 # Pythonスクリプト向けの引数の区切り
    ]
    command.extend(script_args) # スクリプト用の引数を追加

    print("-" * 60)
    print("以下のコマンドでBlenderを起動しようとしています:")
    # コマンドを明確に表示（スペースを含む引数は引用符で囲む）
    print(" ".join(f'"{arg}"' if " " in arg else arg for arg in command))
    print("-" * 60)

    try:
        # Blenderコマンドを実行
        # capture_output=True は標準出力と標準エラーをキャプチャ
        # text=True は標準出力/エラーをテキストとしてデコード（Python 3.7+が必要）
        # check=True はBlenderが0以外のコードで終了した場合にCalledProcessErrorを発生させる
        process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')

        # Blenderスクリプト実行からの出力を表示
        print("\n--- Blender スクリプト出力 (標準出力) ---")
        print(process.stdout if process.stdout else "(標準出力なし)")
        print("------------------------------------")
        if process.stderr:
            # 標準エラー出力に何か含まれている場合のみ表示
            print("\n--- Blender スクリプト出力 (標準エラー) ---")
            print(process.stderr)
            print("------------------------------------")

        print("\nBlenderプロセスは正常に終了しました。")

    except FileNotFoundError:
        # このエラーはblender_exeパス自体が無効な場合に発生（例：タイプミス）
        print(f"エラー: Blenderの起動に失敗しました。コマンド '{blender_exe}' が見つかりませんでした。")
        print(f"       'BLENDER_EXECUTABLE_PATH'が正しいことを確認してください。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # このエラーはBlenderが起動したがエラーコードで終了した場合に発生
        print(f"エラー: Blenderプロセスが終了コード {e.returncode} で失敗しました。")
        print("\n--- Blender スクリプト出力 (標準出力) ---")
        print(e.stdout if e.stdout else "(標準出力なし)")
        print("------------------------------------")
        print("\n--- Blender スクリプト出力 (標準エラー) ---")
        print(e.stderr if e.stderr else "(標準エラー出力なし)")
        print("------------------------------------")
        print("エラーの詳細については、上記のBlender出力を確認してください（例：アドオンが見つからない、スクリプトエラーなど）。")
        sys.exit(1) # Blenderが失敗したためスクリプトを終了
    except Exception as e:
        # サブプロセス実行中のその他の予期しないエラーをキャッチ
        print(f"Blenderの実行中に予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# --- メイン実行ロジック ---
# このスクリプトには2つのモードがあります:
# 1. Pythonで直接実行: Blenderを起動します。
# 2. Blender内部で実行（--python経由）: 変換を実行します。

if __name__ == "__main__":
    # 'bpy'のインポートを試みます。成功すればBlender内部で実行されています。
    # 失敗した場合（ImportError）、標準のPythonインタプリタで実行されています。
    try:
        import bpy
        # --- Blender内部で実行されるコードパス ---
        print("\n>>> Blender環境内で実行中 <<<")

        # Blender内で利用可能な必要なモジュールをインポート
        import glob
        import math
        from mathutils import Matrix # Blenderのmathutilsを使用

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
                args = []
                print("   警告: '--'以降に引数が見つかりません。デフォルト値 'dff', 'fbx' を使用します。")

            dff_dir = args[0] if len(args) > 0 else "dff"
            fbx_dir = args[1] if len(args) > 1 else "fbx"
            options = args[2:]

            # Blender内部でも絶対パスを使用
            dff_dir_abs = os.path.abspath(dff_dir)
            fbx_dir_abs = os.path.abspath(fbx_dir)
            os.makedirs(fbx_dir_abs, exist_ok=True) # 出力ディレクトリが存在することを確認

            print("   --- 内部設定 ---")
            print(f"   入力DFFディレクトリ: {dff_dir_abs}")
            print(f"   出力FBXディレクトリ: {fbx_dir_abs}")
            print(f"   オプション: {options}")
            print("   ----------------------------")

            # --- 2. FBXエクスポート設定の定義 (Maya Y-up) ---
            export_preset = "Maya Y-up"
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
                print(f"   エラー: '{dff_dir_abs}' に *.dff ファイルが見つかりません。変換を中止します。")
                # オプション: エラーコードでBlenderを終了
                # sys.exit(1)
                return # 関数を停止

            print(f"   {len(dff_files)} 個の DFF ファイルが見つかりました。バッチ変換を開始します...")
            processed_count = 0
            error_count = 0

            for i, dff_path in enumerate(dff_files):
                base_name = os.path.splitext(os.path.basename(dff_path))[0]
                fbx_filename = f"{base_name}.fbx"
                fbx_path = os.path.join(fbx_dir_abs, fbx_filename)
                print(f"\n   [{i + 1}/{len(dff_files)}] 処理中: {os.path.basename(dff_path)}")
                try:
                    # --- 3a. 新規シーン ---
                    bpy.ops.wm.read_homefile(use_empty=True)

                    # --- 3b. DFFのインポート ---
                    print(f"     DFFをインポート中...")
                    # 'DragonFF'アドオンが --addons フラグ経由で有効化されていると仮定
                    bpy.ops.import_scene.dff(
                        filepath=dff_path,
                        load_txd=True,
                        load_images=True,
                        connect_bones=False
                    )
                    print(f"     {len(bpy.context.scene.objects)} 個のオブジェクトをインポートしました。")

                    # --- 3c. FBXのエクスポート ---
                    print(f"     FBXを '{fbx_filename}' にエクスポート中...")
                    bpy.ops.export_scene.fbx(
                        filepath=fbx_path,
                        **fbx_export_settings
                    )
                    print(f"   ✓ OK: {os.path.basename(dff_path)} -> {fbx_filename}")
                    processed_count += 1

                except Exception as e:
                    print(f"   ! エラー {os.path.basename(dff_path)} の変換中: {e}")
                    # Blenderの出力内に詳細なトレースバックを表示
                    import traceback
                    traceback.print_exc()
                    error_count += 1
                    # 次のファイルへ進む

            # --- 4. 最終レポート（Blender内部） ---
            print("\n   --- 変換サマリー (Blender内部) ---")
            print(f"   見つかったDFFファイルの総数: {len(dff_files)}")
            print(f"   正常に変換された数: {processed_count}")
            print(f"   発生したエラー数: {error_count}")
            print("   -----------------------------------------")
            print(">>> Blender スクリプト終了 <<<")

        # Blender内で変換関数を実行
        batch_convert_dff_to_fbx_internal()

    except ImportError:
        # --- Blender外部で実行されるコードパス ---
        print("\n>>> Blender環境外で実行中 <<<")
        print("   このスクリプトはBlenderをバックグラウンドで起動し、")
        print("   DFFからFBXへの変換を実行します。")

        # Blender内部で実行されるスクリプト用の引数を準備
        blender_script_arguments = [INPUT_DFF_DIR, OUTPUT_FBX_DIR]
        blender_script_arguments.extend(SCRIPT_OPTIONS)

        # Blenderを起動する関数を呼び出し
        run_blender_script(
            BLENDER_EXECUTABLE_PATH,
            CURRENT_SCRIPT_PATH, # このスクリプトのパスをBlenderに渡す
            REQUIRED_ADDON,
            blender_script_arguments
        )