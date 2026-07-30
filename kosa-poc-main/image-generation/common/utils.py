"""
공통 유틸리티 함수 모음
"""
import re
from PIL import Image
from typing import Union, Optional


def fix_json_escaping(text):
    """
    Gemini 응답에서 잘못된 백슬래시 이스케이프를 수정합니다.
    LaTeX 수식 등에 포함된 백슬래시를 올바르게 이스케이프합니다.

    Args:
        text (str): Gemini의 JSON 응답 텍스트

    Returns:
        str: 수정된 JSON 텍스트
    """
    # JSON 문자열 값 내부의 모든 백슬래시를 올바르게 이스케이프
    def escape_backslashes_in_string(match):
        string_content = match.group(0)
        quote = string_content[0]
        content = string_content[1:-1]

        # 방법: 모든 백슬래시를 임시로 플레이스홀더로 교체 -> 이중 백슬래시로 변환 -> 유효한 이스케이프는 원래대로
        # 더 간단한 방법: 백슬래시를 순차적으로 처리

        # 1단계: 모든 \를 임시 플레이스홀더로 변환
        temp_placeholder = "###BACKSLASH###"
        content = content.replace("\\", temp_placeholder)

        # 2단계: 플레이스홀더를 \\로 변환 (JSON에서 \를 표현)
        content = content.replace(temp_placeholder, "\\\\")

        return f'{quote}{content}{quote}'

    # JSON 문자열 값을 찾는 정규식
    # 이중 따옴표 문자열만 처리 (JSON 표준)
    fixed_text = re.sub(
        r'"(?:[^"\\]|\\.)*"',
        escape_backslashes_in_string,
        text
    )

    return fixed_text


def load_image(image_path: str) -> Image.Image:
    """
    이미지 파일을 로드

    Args:
        image_path: 이미지 파일 경로

    Returns:
        PIL Image 객체
    """
    try:
        image = Image.open(image_path)
        return image.convert('RGB')
    except Exception as e:
        raise ValueError(f"이미지 로드 실패: {image_path}, 오류: {str(e)}")


def save_image(image: Union[Image.Image, str], output_path: str) -> None:
    """
    이미지를 파일로 저장

    Args:
        image: PIL Image 객체 또는 이미지 경로
        output_path: 저장할 경로
    """
    try:
        if isinstance(image, str):
            # 이미지 경로가 주어진 경우
            img = Image.open(image)
        else:
            img = image

        # 디렉토리 생성
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 이미지 저장
        img.save(output_path)

    except Exception as e:
        raise ValueError(f"이미지 저장 실패: {output_path}, 오류: {str(e)}")


def find_resource_path(filename: str) -> Optional[str]:
    """
    resource 디렉토리 내에서 해당 파일의 실제 경로를 찾음
    Args:
        filename: 찾고자 하는 파일명
    Returns:
        찾은 경우 파일 경로, 못 찾은 경우 None
    """
    import os
    resource_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resource")
    clean_filename = filename

    for prefix in ['ref_', 'prod_', 'bg_removed_', 'fabric_']:
        if clean_filename.startswith(prefix):
            clean_filename = clean_filename[len(prefix):]
            break

    for root, dirs, files in os.walk(resource_dir):
        if clean_filename in files:
            return os.path.join(root, clean_filename)

    return None


def get_unique_filepath(filepath: str) -> str:
    """
    파일이 이미 존재하는 경우 _{number}를 붙여서 고유한 파일명을 반환

    Args:
        filepath: 원본 파일 경로

    Returns:
        고유한 파일 경로 (존재하지 않는 경로)

    Examples:
        chair_01.png가 이미 존재하면 -> chair_01_1.png
        chair_01_1.png도 존재하면 -> chair_01_2.png
    """
    import os

    if not os.path.exists(filepath):
        return filepath

    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)

    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        new_filepath = os.path.join(directory, new_filename)

        if not os.path.exists(new_filepath):
            return new_filepath

        counter += 1


def get_unique_filepath_pair(image_path: str, json_path: str) -> tuple[str, str]:
    """
    PNG와 JSON 파일 쌍이 이미 존재하는 경우 둘 다 _{number}를 붙여서 고유한 파일명 쌍을 반환

    Args:
        image_path: 이미지 파일 경로
        json_path: JSON 파일 경로

    Returns:
        (고유한 이미지 경로, 고유한 JSON 경로) 튜플

    Examples:
        chair_01.png, chair_01.json이 이미 존재하면
        -> (chair_01_1.png, chair_01_1.json)
    """
    import os

    # 둘 다 존재하지 않으면 원본 반환
    if not os.path.exists(image_path) and not os.path.exists(json_path):
        return image_path, json_path

    # 이미지 파일 경로 분리
    img_directory = os.path.dirname(image_path)
    img_filename = os.path.basename(image_path)
    img_name, img_ext = os.path.splitext(img_filename)

    # JSON 파일 경로 분리
    json_directory = os.path.dirname(json_path)
    json_filename = os.path.basename(json_path)
    json_name, json_ext = os.path.splitext(json_filename)

    counter = 1
    while True:
        new_img_filename = f"{img_name}_{counter}{img_ext}"
        new_img_path = os.path.join(img_directory, new_img_filename)

        new_json_filename = f"{json_name}_{counter}{json_ext}"
        new_json_path = os.path.join(json_directory, new_json_filename)

        # 둘 다 존재하지 않으면 반환
        if not os.path.exists(new_img_path) and not os.path.exists(new_json_path):
            return new_img_path, new_json_path

        counter += 1