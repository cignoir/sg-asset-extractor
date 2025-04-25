# SG Asset Extractor
## 汎用
```bash
# まとめて
unpack_all.bat
```

または

```bash
# 個別に
python unpack.py bin/AnimInfo_024.bin bin/Anim_024.bin output/anim
python unpack.py bin/ClumpInfo_128.bin bin/Clump_128.bin output/clump
python unpack.py bin/IdTblInfo_002.bin bin/IdTbl_002.bin output/idtbl
python unpack.py bin/PrtInfo_011.bin bin/Prt_011.bin output/prt
python unpack.py bin/SEInfo_002.bin bin/SE_002.bin output/se
python unpack.py bin/TexInfo_193.bin bin/Tex_193.bin output/tex
python unpack.py bin/WindowInfo_101.bin bin/Window_101.bin output/window
```

## テクスチャ抽出(png)
```bash
python unpack_png.py
```
  
## fbx変換

* Pythonライブラリ: `pip install numpy Pillow`
* BlenderのインストールとDragonFFアドオンの有効化
* `python convert_dff_to_fbx.py "path/to/blender-executable" output/clump output/fbx`

## hexdump生成
```bash
python hexdump.py bin/Clump_128.bin --limit 100
```

* limitは出力ファイルのサイズ制限(MB)。引数なしは無制限。