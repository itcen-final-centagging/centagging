import { useState } from 'react';
import { ArrowLeft, Check, Save } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { ImagePreview } from '@/features/tagging/components/ImagePreview';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { TaggingValues } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const categories = ['소파', '테이블', '의자', '수납', '조명'];
const colors = ['그레이', '베이지', '화이트', '블랙', '브라운'];
const materials = ['패브릭', '가죽', '원목', '메탈', '플라스틱'];
const styleTags = [
  'null',
  '모던',
  '미니멀',
  '내추럴',
  '컨템포러리',
  '라운드',
  '패브릭',
];

interface MetadataRowProps {
  label: string;
  value: string;
}

const MetadataRow = ({ label, value }: MetadataRowProps) => (
  <div className="flex items-center justify-between border-b border-neutral-100 py-3 last:border-b-0">
    <span className="text-xs text-neutral-500">{label}</span>
    <span className="max-w-[65%] text-right text-xs font-bold text-neutral-700">
      {value}
    </span>
  </div>
);

const getMetadataText = (
  attributes: Record<string, unknown> | undefined,
  key: string,
  fallback: string,
): string => {
  const value = attributes?.[key];
  return typeof value === 'string' && value ? value : fallback;
};

export const ReviewPanel = () => {
  const {
    changeStage,
    saveTagging,
    selectedObject,
    selectedSku,
    uploadedImage,
  } = useTaggingWorkflow();

  const [values, setValues] = useState<TaggingValues>({
    category:
      selectedObject?.metadata.category ?? selectedSku?.category ?? 'null',
    color: getMetadataText(
      selectedObject?.metadata.attributes,
      'color',
      selectedSku?.color ?? 'null',
    ),
    material: getMetadataText(
      selectedObject?.metadata.attributes,
      'material',
      selectedSku?.material ?? 'null',
    ),
    mood: selectedObject?.metadata.description ?? 'null',
    styleTags: selectedObject?.metadata.keyFeatures.length
      ? selectedObject.metadata.keyFeatures.slice(0, 3)
      : ['null'],
  });

  if (!selectedSku) return null;

  const handleChangeValue = <Key extends keyof TaggingValues>(
    key: Key,
    value: TaggingValues[Key],
  ): void => {
    setValues((currentValues) => ({ ...currentValues, [key]: value }));
  };

  const handleToggleTag = (tag: string): void => {
    handleChangeValue(
      'styleTags',
      values.styleTags.includes(tag)
        ? values.styleTags.filter((currentTag) => currentTag !== tag)
        : [...values.styleTags, tag],
    );
  };

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(320px,1.12fr)]">
      <article className="studio-surface p-5">
        <h2 className="text-base font-extrabold text-neutral-800">선택 객체</h2>
        <p className="mt-4 text-xs font-bold text-neutral-500">원본 이미지</p>
        <div className="mt-2">
          <ImagePreview
            image={uploadedImage}
            objects={selectedObject ? [selectedObject] : []}
            selectedObject={selectedObject}
            showBoxes
          />
        </div>
        <p className="mt-4 text-xs font-bold text-neutral-500">
          AI가 추출한 객체
        </p>
        <FurnitureArtwork
          className="mt-2"
          imageUrl={selectedSku.imageUrl}
          kind={selectedSku.kind}
        />
        <p className="mt-2 text-sm font-bold text-neutral-700">
          {selectedObject?.name ?? '선택 객체'}
        </p>
      </article>
      <article className="studio-surface p-5">
        <h2 className="text-base font-extrabold text-neutral-800">선택 SKU</h2>
        <FurnitureArtwork
          className="mt-4"
          imageUrl={selectedSku.imageUrl}
          kind={selectedSku.kind}
        />
        <p className="mt-4 font-mono text-xs font-bold text-neutral-400">
          {selectedSku.sku}
        </p>
        <p className="mt-1 text-base font-extrabold text-neutral-800">
          {selectedSku.name}
        </p>
        <dl className="mt-4">
          <MetadataRow label="카테고리" value={values.category} />
          <MetadataRow label="색상" value={selectedSku.color ?? 'null'} />
          <MetadataRow label="소재" value={selectedSku.material ?? 'null'} />
          <MetadataRow label="규격" value={selectedSku.size ?? 'null'} />
        </dl>
      </article>
      <article className="studio-surface p-5">
        <h2 className="text-base font-extrabold text-neutral-800">
          AI 태깅 정보
        </h2>
        <p className="mt-1.5 text-sm text-neutral-500">
          필수 태그를 확인하고 필요한 경우 수정해 주세요.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
          <label className="text-sm font-bold text-neutral-700">
            가구 카테고리
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('category', event.target.value)
              }
              value={values.category}
            >
              <option value="null">null</option>
              {categories.map((category) => (
                <option key={category}>{category}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-bold text-neutral-700">
            대표 색상
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('color', event.target.value)
              }
              value={values.color}
            >
              <option value="null">null</option>
              {colors.map((color) => (
                <option key={color}>{color}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-bold text-neutral-700">
            주요 소재
            <select
              className="mt-2 h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
              onChange={(event) =>
                handleChangeValue('material', event.target.value)
              }
              value={values.material}
            >
              <option value="null">null</option>
              {materials.map((material) => (
                <option key={material}>{material}</option>
              ))}
            </select>
          </label>
        </div>
        <fieldset className="mt-5">
          <legend className="text-sm font-bold text-neutral-700">
            스타일 태그
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {styleTags.map((tag) => {
              const isSelected = values.styleTags.includes(tag);
              return (
                <button
                  className={cn(
                    'rounded-full border px-3 py-1.5 text-xs font-bold transition-colors',
                    isSelected
                      ? 'border-primary-300 bg-primary-20 text-primary-700'
                      : 'border-neutral-200 bg-white text-neutral-500 hover:bg-neutral-50',
                  )}
                  key={tag}
                  onClick={() => handleToggleTag(tag)}
                  type="button"
                >
                  {isSelected ? (
                    <Check className="mr-1 inline" size={12} />
                  ) : null}
                  {tag}
                </button>
              );
            })}
          </div>
        </fieldset>
        <label className="mt-5 block text-sm font-bold text-neutral-700">
          공간 분위기
          <textarea
            className="mt-2 min-h-21 w-full resize-y rounded-md border border-neutral-200 bg-white p-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
            maxLength={100}
            onChange={(event) => handleChangeValue('mood', event.target.value)}
            value={values.mood}
          />
        </label>
      </article>
      <div className="col-span-full grid gap-3 sm:grid-cols-2">
        <Button
          fullWidth
          onClick={() => changeStage('recommend')}
          startDecorator={<ArrowLeft size={17} />}
          variant="neutral-outlined"
        >
          SKU 다시 선택
        </Button>
        <Button
          endDecorator={<Save size={17} />}
          fullWidth
          onClick={() => void saveTagging()}
        >
          태깅 결과 저장
        </Button>
      </div>
    </section>
  );
};
