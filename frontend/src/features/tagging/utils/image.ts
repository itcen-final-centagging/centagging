import { MAX_FILE_SIZE, MIN_IMAGE_DIMENSION } from '../constants/data';

import type { UploadedImage } from '../types';

const ACCEPTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png']);

const readImageDimensions = (
  file: File,
): Promise<{ height: number; width: number }> =>
  new Promise((resolve, reject) => {
    const previewUrl = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      URL.revokeObjectURL(previewUrl);
      resolve({ height: image.height, width: image.width });
    };
    image.onerror = () => {
      URL.revokeObjectURL(previewUrl);
      reject(
        new Error('이미지를 읽을 수 없습니다. 다른 파일을 선택해 주세요.'),
      );
    };
    image.src = previewUrl;
  });

export const validateImage = async (file: File): Promise<UploadedImage> => {
  if (!ACCEPTED_IMAGE_TYPES.has(file.type)) {
    throw new Error('JPG, PNG 파일만 업로드 가능합니다.');
  }
  if (file.size > MAX_FILE_SIZE) {
    throw new Error('파일 용량은 최대 10MB까지 가능합니다.');
  }

  const { height, width } = await readImageDimensions(file);
  if (width < MIN_IMAGE_DIMENSION || height < MIN_IMAGE_DIMENSION) {
    throw new Error('가로와 세로가 512px 이상인 이미지를 업로드해 주세요.');
  }

  return {
    file,
    height,
    name: file.name,
    previewUrl: URL.createObjectURL(file),
    size: file.size,
    width,
  };
};

export const formatFileSize = (size: number): string => {
  const megaBytes = size / 1024 / 1024;
  return `${megaBytes.toFixed(1)}MB`;
};
