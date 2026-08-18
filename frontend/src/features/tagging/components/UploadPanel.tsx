import {
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
} from 'react';
import {
  ImagePlus,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { ImagePreview } from '@/features/tagging/components/ImagePreview';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import { formatFileSize } from '@/features/tagging/utils/image';
import { cn } from '@/lib/utils';

export const UploadPanel = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const {
    beginAnalysis,
    clearUploadError,
    loadDemoWorkflow,
    uploadError,
    uploadedImage,
    uploadImage,
  } = useTaggingWorkflow();

  const handleFile = async (file?: File): Promise<void> => {
    if (!file) return;
    await uploadImage(file);
  };

  const handleInputChange = async (
    event: ChangeEvent<HTMLInputElement>,
  ): Promise<void> => {
    await handleFile(event.target.files?.[0]);
    event.target.value = '';
  };

  const handleDrop = async (
    event: DragEvent<HTMLDivElement>,
  ): Promise<void> => {
    event.preventDefault();
    setIsDragging(false);
    await handleFile(event.dataTransfer.files[0]);
  };

  const handleUploadAreaClick = (): void => {
    fileInputRef.current?.click();
  };

  const handleUploadAreaKeyDown = (
    event: KeyboardEvent<HTMLDivElement>,
  ): void => {
    if (event.key === 'Enter' || event.key === ' ') {
      handleUploadAreaClick();
    }
  };

  const handleAnalysisStart = (): void => {
    void beginAnalysis();
  };

  const handleDemoWorkflowStart = (): void => {
    void loadDemoWorkflow();
  };

  const isAnalyzing = false;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <section className="studio-surface p-6">
        <div>
          <h2 className="text-base font-extrabold text-neutral-800">
            연출 이미지 업로드
          </h2>
          <p className="mt-1.5 text-sm text-neutral-500">
            JPG 또는 PNG 형식, 최대 10MB, 최소 512 × 512px
          </p>
        </div>
        <div
          className={cn(
            'mt-5 flex min-h-[224px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors',
            isDragging
              ? 'border-primary bg-primary-20'
              : 'border-blue-300 bg-bg-tertiary hover:border-blue-500 hover:bg-white',
          )}
          onClick={handleUploadAreaClick}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          onKeyDown={handleUploadAreaKeyDown}
        >
          <span className="flex size-16 items-center justify-center rounded-full bg-white text-blue-700 shadow-sm">
            <UploadCloud size={30} strokeWidth={2.15} />
          </span>
          <p className="mt-4 text-base font-bold text-text-primary">
            이미지를 끌어다 놓거나 선택해 주세요
          </p>
          <p className="mt-1 text-xs text-neutral-400">JPG, PNG · 최대 10MB</p>
          <input
            accept="image/jpeg,image/png"
            className="hidden"
            onChange={handleInputChange}
            ref={fileInputRef}
            type="file"
          />
        </div>
        {uploadError ? (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-danger-200 bg-danger-20 px-3 py-2.5 text-sm text-danger-600">
            <span>{uploadError}</span>
            <button
              className="font-bold underline"
              onClick={clearUploadError}
              type="button"
            >
              닫기
            </button>
          </div>
        ) : null}
        {uploadedImage ? (
          <>
            <div className="mt-5 flex flex-wrap items-center gap-2 rounded-lg border border-neutral-100 bg-neutral-20 px-3 py-2.5 text-sm text-neutral-600">
              <ImagePlus size={16} className="text-primary" />
              <span className="font-semibold">{uploadedImage.name}</span>
              <span className="text-neutral-400">·</span>
              <span>
                {uploadedImage.width} × {uploadedImage.height}px
              </span>
              <span className="text-neutral-400">·</span>
              <span>{formatFileSize(uploadedImage.size)}</span>
              <span className="rounded-full bg-success-50 px-2 py-1 text-xs font-bold text-success-600">
                업로드 준비 완료
              </span>
            </div>
            <div className="mt-4">
              <ImagePreview image={uploadedImage} />
            </div>
          </>
        ) : null}
        <Button
          className="mt-5"
          disabled={!uploadedImage || isAnalyzing}
          fullWidth
          onClick={handleAnalysisStart}
          size="lg"
          startDecorator={
            isAnalyzing ? (
              <LoaderCircle className="animate-spin" size={18} />
            ) : (
              <ImagePlus size={18} />
            )
          }
        >
          AI 분석 시작
        </Button>
        <Button
          className="mt-3"
          fullWidth
          onClick={handleDemoWorkflowStart}
          size="lg"
          startDecorator={<Sparkles size={18} />}
          variant="neutral-outlined"
        >
          데모로 객체 · SKU 선택 보기
        </Button>
        <p className="mt-2 text-center text-xs leading-5 text-text-tertiary">
          AI 호출 없이 소파 객체 선택과 SKU 후보 비교 화면을 바로 확인합니다.
        </p>
      </section>

      <aside className="studio-surface h-fit p-6">
        <h2 className="text-base font-extrabold text-neutral-800">작업 안내</h2>
        <p className="mt-1.5 text-sm leading-6 text-neutral-500">
          한 이미지에서 하나의 가구를 선택해 상품을 연결합니다.
        </p>
        <ol className="mt-6 space-y-5">
          {[
            [
              '1',
              '이미지를 업로드해요',
              '공간과 가구가 선명하게 보이는 이미지를 선택해 주세요.',
            ],
            [
              '2',
              '탐지한 가구를 선택해요',
              'AI가 찾은 가구 중 태깅할 객체 하나를 골라요.',
            ],
            [
              '3',
              'SKU와 태그를 검수해요',
              '추천 근거를 확인한 뒤 최종 결과를 저장해요.',
            ],
          ].map(([number, title, description]) => (
            <li className="flex gap-3" key={number}>
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-20 text-xs font-extrabold text-primary">
                {number}
              </span>
              <div>
                <p className="text-sm font-bold text-neutral-700">{title}</p>
                <p className="mt-1 text-xs leading-5 text-neutral-500">
                  {description}
                </p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-6 flex gap-2 rounded-lg bg-neutral-20 p-3 text-xs leading-5 text-neutral-500">
          <ShieldCheck className="mt-0.5 shrink-0 text-primary" size={16} />
          이미지는 현재 작업과 검수에 필요한 범위에서만 사용됩니다.
        </div>
      </aside>
    </div>
  );
};
