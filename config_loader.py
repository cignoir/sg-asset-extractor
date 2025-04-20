# config_loader.py
import configparser
import os
import sys

def load_config(ini_filename='config.ini'):
    """指定されたINIファイルから設定を読み込みます。"""
    config = configparser.ConfigParser()
    # INIファイルパスを決定 (スクリプト基準 or カレントディレクトリ)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ini_path = os.path.join(script_dir, ini_filename)
    except NameError:
        ini_path = os.path.join(os.getcwd(), ini_filename)

    if not os.path.exists(ini_path):
        print(f"エラー: 設定ファイル '{ini_filename}' が見つかりません。\n       検索パス: {os.path.abspath(ini_path)}", file=sys.stderr)
        sys.exit(1)

    try:
        config.read(ini_path, encoding='utf-8')
        print(f"設定ファイルを読み込みました: {ini_path}")
        # configオブジェクトとiniファイルのディレクトリを返す
        return config, os.path.dirname(ini_path)
    except configparser.Error as e:
        print(f"エラー: 設定ファイル '{ini_path}' の読み込みエラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期せぬエラー: 設定ファイル読み込み中: {e}", file=sys.stderr)
        sys.exit(1)

def get_path_from_config(config, ini_dir, section, key, is_dir=False, create_dir=False):
    """設定からパスを取得し、INIファイルのディレクトリ基準で相対パスを解決します。"""
    path_str = config.get(section, key, fallback=None)
    if path_str is None:
        print(f"警告: 設定 [{section}] '{key}' が見つかりません。", file=sys.stderr)
        return None

    # 絶対パスでなければini基準で解決
    if not os.path.isabs(path_str):
        resolved_path = os.path.join(ini_dir, path_str)
    else:
        resolved_path = path_str

    resolved_path = os.path.normpath(resolved_path)

    # ディレクトリの場合、必要なら作成
    if is_dir and create_dir and not os.path.exists(resolved_path):
        try:
            os.makedirs(resolved_path)
            print(f"ディレクトリを作成しました: {resolved_path}")
        except OSError as e:
            print(f"エラー: ディレクトリ作成失敗: {resolved_path}\n{e}", file=sys.stderr)
            return None

    return resolved_path