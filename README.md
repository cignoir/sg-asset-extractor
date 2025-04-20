# SG Asset Extractor

## 共通設定

各種binや出力先ディレクトリのパスを `config.ini` に記述します。
Blenderのexeパスはdff→fbx変換したい場合のみ必要です。

## テクスチャ抽出

実行コマンド: `python extract_textures.py`

## 3Dモデル(dff)抽出

実行コマンド: `python extract_clumps.py`

### Requirements

* Pythonライブラリ: `pip install numpy Pillow`
* BlenderのインストールとDragonFFアドオンの有効化
* `config.ini` にBlenderのexeパスを設定
  
## dff→fbx変換

実行コマンド: `python convert_dff_to_fbx.py`

## SE抽出

実行コマンド: `python extract_se.py`

* SEはwavとsgtの2種類

## Anim抽出

実行コマンド: `python extract_ame.py`

## StA/StB/StC
拡張子を .wav に変更
