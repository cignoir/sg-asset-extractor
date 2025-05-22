# -*- coding: utf-8 -*-
import struct
import io
import math
import traceback
import os
import sys
import binascii

# OpenMaya API をスタンドアロンで使用するためにmaya.standaloneを初期化
# (Mayaがインストールされている環境で実行する必要があります)
try:
    import maya.standalone
    maya.standalone.initialize(name='python')
    import maya.api.OpenMaya as om
    print("Successfully initialized OpenMaya standalone.")
    MAYA_INITIALIZED = True
except ImportError as e:
    print(f"Error importing maya.standalone or maya.api.OpenMaya: {e}")
    print("Please ensure Maya is installed and its Python environment is accessible.")
    print("Cannot perform calculations without OpenMaya.")
    om = None
    MAYA_INITIALIZED = False
    # Exit if Maya API not available, as calculations depend on it.
    sys.exit(1)
except Exception as e:
    print(f"Error initializing maya.standalone: {e}")
    om = None
    MAYA_INITIALIZED = False
    sys.exit(1)


# --- 定数 ---
RWCHUNK_STRUCT_ID = 0x01
RWCHUNK_EXTENSION_ID = 0x03
RWCHUNK_FRAMELIST_ID = 0x0E
RWCHUNK_CLUMP_ID = 0x10
RWCHUNK_HANIMPLG_ID = 0x11E # HAnim Plugin ID

FRAME_DATA_SIZE = 56
FRAME_DATA_FORMAT = '<9f 3f i I' # Matrix(9f) + Pos(3f) + ParentIdx(i) + Unknown(I)

# 計算オプション (必要に応じて変更)
DEFAULT_MAYA_SCALE_FACTOR = 100.0 # DFF座標からMaya座標へのスケール係数
DEFAULT_TARGET_ROTATE_ORDER = 'xyz' # 出力するオイラー角の回転順序
TARGET_MAYA_AXIS = '-z_up_+y_front' # Mayaのターゲット座標系を指定

# --- DFF解析関数 (変更なし) ---
def read_chunk_header(stream):
    header_bytes = stream.read(12)
    if len(header_bytes) < 12: return None, None, None
    return struct.unpack('<III', header_bytes)

def find_chunk_data(stream, target_chunk_id, search_limit):
    chunk_data = None; start_search_pos = stream.tell()
    try:
        while stream.tell() < search_limit:
            chunk_start_pos = stream.tell(); chunk_id, chunk_size, chunk_version = read_chunk_header(stream)
            if chunk_id is None: break
            chunk_data_start_pos = stream.tell(); chunk_data_end_pos = chunk_data_start_pos + chunk_size
            if chunk_data_end_pos > search_limit: print(f"W: Chunk {chunk_id:#04x}@{chunk_start_pos:#x} size {chunk_size} exceeds limit {search_limit:#x}."); stream.seek(chunk_start_pos); return None
            if chunk_id == target_chunk_id:
                chunk_data = stream.read(chunk_size)
                if len(chunk_data) < chunk_size: print(f"W: Incomplete read for target chunk {chunk_id:#04x}."); chunk_data = None
                break
            else: stream.seek(chunk_data_start_pos + chunk_size)
    except Exception as e: print(f"E: Chunk search: {e}"); traceback.print_exc(); chunk_data = None
    return chunk_data

def parse_frame_struct_data(frame_struct_data):
    frames = []; data_stream = io.BytesIO(frame_struct_data)
    try:
        count_bytes = data_stream.read(4); frame_count = struct.unpack('<I', count_bytes)[0]
        print(f"Frame count in FrameList Struct: {frame_count}");
        if frame_count == 0: return []
        expected_data_size = 4 + frame_count * FRAME_DATA_SIZE; actual_data_size = len(frame_struct_data)
        if actual_data_size < expected_data_size: print(f"W: Struct data size {actual_data_size} < expected {expected_data_size}."); frame_count = (actual_data_size - 4) // FRAME_DATA_SIZE; print(f"  -> Reading {frame_count} frames.");
        if frame_count <= 0: return []
        for i in range(frame_count):
            frame_data_bytes = data_stream.read(FRAME_DATA_SIZE);
            if len(frame_data_bytes) < FRAME_DATA_SIZE: print(f"W: EOF reading frame {i+1}."); break
            unpacked_data = struct.unpack(FRAME_DATA_FORMAT, frame_data_bytes)
            frame_info = {
                "id": i + 1,
                "raw_matrix": unpacked_data[0:9],
                "raw_position": unpacked_data[9:12],
                "parent_id": unpacked_data[12] + 1 if unpacked_data[12] != -1 else 0,
                "unknown_int": unpacked_data[13]
            }
            frames.append(frame_info)
    except Exception as e: print(f"E: Parsing frame struct: {e}"); traceback.print_exc(); return []
    return frames

def load_dff_framelist(dff_file_path):
    parsed_frames = [];
    try:
        with open(dff_file_path, 'rb') as dff_stream:
            print(f"Opening DFF file: {dff_file_path}")
            dff_stream.seek(0, io.SEEK_END); file_size = dff_stream.tell(); dff_stream.seek(0, io.SEEK_SET)
            print(f"File size: {file_size} bytes")
            clump_id, clump_size, clump_version = read_chunk_header(dff_stream)
            if clump_id != RWCHUNK_CLUMP_ID: raise ValueError(f"Not Clump. Found: {clump_id:#04x}")
            print(f"Found Clump chunk (ID: {clump_id:#04x}, Size: {clump_size})")
            clump_data_start_pos = dff_stream.tell(); clump_data_limit = min(clump_data_start_pos + clump_size, file_size)
            framelist_data = find_chunk_data(dff_stream, RWCHUNK_FRAMELIST_ID, clump_data_limit)
            if framelist_data:
                print(f"FrameList chunk (ID: {RWCHUNK_FRAMELIST_ID:#04x}) found.")
                framelist_stream = io.BytesIO(framelist_data); framelist_limit = len(framelist_data)
                struct_data = find_chunk_data(framelist_stream, RWCHUNK_STRUCT_ID, framelist_limit)
                if struct_data:
                    print(f"FrameList Struct chunk (ID: {RWCHUNK_STRUCT_ID:#04x}) found.")
                    parsed_frames = parse_frame_struct_data(struct_data)
                else: print("E: Struct chunk not found within FrameList."); return []
            else: print("E: FrameList chunk not found in Clump.")
    except FileNotFoundError: print(f"E: DFF file not found: '{dff_file_path}'")
    except Exception as e: print(f"E: Processing DFF: {e}"); traceback.print_exc()
    return parsed_frames

# --- 行列・ベクトル演算関数 ---

def build_local_matrix_om(dff_frame, scale_factor):
    """DFFフレームデータからローカル変換行列(MMatrix)を構築 (スケール適用)"""
    if not om: return None
    r = dff_frame['raw_matrix'][0:3]; u = dff_frame['raw_matrix'][3:6]; a = dff_frame['raw_matrix'][6:9]
    p_raw = dff_frame['raw_position']
    p_scaled = [p * scale_factor for p in p_raw]
    matrix_list = [ r[0], r[1], r[2], 0.0, u[0], u[1], u[2], 0.0, a[0], a[1], a[2], 0.0, p_scaled[0], p_scaled[1], p_scaled[2], 1.0 ]
    return om.MMatrix(matrix_list)

def get_world_transform_om(frame_id, dff_frame_map, local_transforms, world_transforms):
    """フレームIDのワールド変換行列を再帰的に計算 (OpenMaya版)"""
    if not om: return None
    if frame_id in world_transforms: return world_transforms[frame_id]
    if frame_id not in dff_frame_map: print(f"E: Frame ID {frame_id} not found."); return om.MMatrix()
    dff_frame = dff_frame_map[frame_id]
    local_tfm_matrix = local_transforms.get(frame_id)
    if local_tfm_matrix is None: print(f"E: Local transform for Frame {frame_id} not calculated."); return om.MMatrix()

    parent_id = dff_frame['parent_id']

    if parent_id == 0: # Root frame
        world_tfm_matrix = local_tfm_matrix
        # Apply global DFF(Z-up) to Maya(-Z up, +Y front) conversion at the root
        # This corresponds to a +180 degree rotation around the X-axis.
        rot_x_180_rad = math.radians(180.0) # Changed rotation to 180 deg X
        cos_a = math.cos(rot_x_180_rad); sin_a = math.sin(rot_x_180_rad) # cos(180)=-1, sin(180)=0
        x_rot_matrix_list = [ 1.0, 0.0,   0.0,  0.0, 0.0, cos_a, sin_a, 0.0, 0.0,-sin_a, cos_a, 0.0, 0.0, 0.0,   0.0,  1.0 ]
        # Results in: [1,0,0,0, 0,-1,0,0, 0,0,-1,0, 0,0,0,1]
        x_rot_matrix = om.MMatrix(x_rot_matrix_list)
        # Pre-multiply: World = Conversion * LocalRoot
        world_tfm_matrix = x_rot_matrix * world_tfm_matrix
    else:
        parent_world_tfm_matrix = get_world_transform_om(parent_id, dff_frame_map, local_transforms, world_transforms)
        if parent_world_tfm_matrix is None: return om.MMatrix()
        # World = ParentWorld * Local
        world_tfm_matrix = parent_world_tfm_matrix * local_tfm_matrix

    world_transforms[frame_id] = world_tfm_matrix
    return world_tfm_matrix

def extract_pos_rot_from_matrix_om(world_matrix, rotate_order_str):
    """ワールド行列(MMatrix)から位置とオイラー角(度)を抽出"""
    if not om: return (0,0,0), (0,0,0)
    try:
        transform = om.MTransformationMatrix(world_matrix)
        pos = transform.translation(om.MSpace.kWorld)
        euler_rotation = transform.rotation(asQuaternion=False)
        ro_map = {'xyz': om.MTransformationMatrix.kXYZ, 'yzx': om.MTransformationMatrix.kYZX, 'zxy': om.MTransformationMatrix.kZXY, 'xzy': om.MTransformationMatrix.kXZY, 'yxz': om.MTransformationMatrix.kYXZ, 'zyx': om.MTransformationMatrix.kZYX}
        rotate_order_enum = ro_map.get(rotate_order_str.lower(), om.MTransformationMatrix.kXYZ)
        euler_rotation.reorderIt(rotate_order_enum)
        rot_deg = [math.degrees(angle) for angle in [euler_rotation.x, euler_rotation.y, euler_rotation.z]]
        return (pos.x, pos.y, pos.z), rot_deg
    except Exception as e:
        print(f"E: Extracting transform: {e}"); return (0,0,0), (0,0,0)

# --- メイン実行関数 ---
def calculate_and_print_world_coords(dff_file_path, scale_factor, rotate_order):
    """DFFを読み込み、全フレームのワールド座標を計算して表示する"""
    if not MAYA_INITIALIZED: print("E: OpenMaya not available."); return

    dff_frames = load_dff_framelist(dff_file_path)
    if not dff_frames: print("Failed to load DFF FrameList."); return
    dff_frame_map = {frame['id']: frame for frame in dff_frames}

    local_transforms = {}
    for frame in dff_frames:
        local_matrix = build_local_matrix_om(frame, scale_factor)
        if local_matrix is None: print(f"E: Building local matrix for Frame {frame['id']}. Aborting."); return
        local_transforms[frame['id']] = local_matrix

    world_transforms = {}
    print(f"\nCalculating world transforms (Target: Maya {TARGET_MAYA_AXIS})...") # Updated target description
    for frame_id in dff_frame_map.keys():
        get_world_transform_om(frame_id, dff_frame_map, local_transforms, world_transforms)
    print("World transform calculation complete.")

    print(f"\n--- Calculated World Coordinates (Scale: {scale_factor}, Target Maya Axis: {TARGET_MAYA_AXIS}, Rotate Order: {rotate_order}) ---")
    sorted_frame_ids = sorted(dff_frame_map.keys())
    for frame_id in sorted_frame_ids:
        world_matrix = world_transforms.get(frame_id)
        if world_matrix:
            world_pos, world_rot_deg = extract_pos_rot_from_matrix_om(world_matrix, rotate_order)
            parent_id = dff_frame_map[frame_id]['parent_id']
            parent_str = f"Parent: {parent_id}" if parent_id != 0 else "Parent: ROOT"
            print("-" * 20)
            print(f"[Frame {frame_id}] ({parent_str})")
            print(f"  World Position = ({world_pos[0]:.3f}, {world_pos[1]:.3f}, {world_pos[2]:.3f})")
            print(f"  World Rotation ({rotate_order.upper()}) = ({world_rot_deg[0]:.3f}, {world_rot_deg[1]:.3f}, {world_rot_deg[2]:.3f})")
        else: print(f"[Frame {frame_id}] - Error calculating world transform.")
    print("-" * 20)

# --- スクリプト実行 ---
if __name__ == "__main__":
    if len(sys.argv) > 1: input_dff_path = sys.argv[1]
    else:
        default_path = "H:/workspace/sg-asset-extractor/output/フロッピー/001_005_00003.dff" # Provide a default or leave empty
        input_dff_path = input(f"Enter DFF file path [{default_path}]: ") or default_path

    if input_dff_path and os.path.exists(input_dff_path):
        calculate_and_print_world_coords(
            input_dff_path,
            DEFAULT_MAYA_SCALE_FACTOR,
            DEFAULT_TARGET_ROTATE_ORDER
        )
    elif not input_dff_path: print("No DFF file path provided.")
    else: print(f"Error: File not found at '{input_dff_path}'")

    if MAYA_INITIALIZED:
        try: maya.standalone.uninitialize(); print("Maya standalone uninitialized.")
        except Exception as e: print(f"Error uninitializing maya.standalone: {e}")

