import { useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  Search,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/commons/components/Button';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';

interface LoadingPanelProps {
  label: string;
  description: string;
}

export const LoadingPanel = ({ label, description }: LoadingPanelProps) => (
  <div className="studio-surface flex min-h-90 flex-col items-center justify-center text-center">
    <span className="flex size-16 items-center justify-center rounded-full bg-primary-20 text-primary">
      <LoaderCircle className="animate-spin" size={29} />
    </span>
    <h2 className="mt-5 text-xl font-extrabold text-neutral-800">{label}</h2>
    <p className="mt-2 text-sm text-neutral-500">{description}</p>
  </div>
);

export const NoDetectionPanel = () => {
  const { changeStage, redetect } = useTaggingWorkflow();
  const [description, setDescription] = useState('');
  const isValid = description.trim().length >= 2;

  return (
    <section className="mx-auto max-w-2xl">
      <div className="studio-surface flex min-h-75 flex-col items-center justify-center px-7 text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary-20 text-primary">
          <Search size={28} />
        </span>
        <h2 className="mt-5 text-xl font-extrabold text-neutral-800">
          탐지된 가구가 없습니다
        </h2>
        <p className="mt-2 text-sm leading-6 text-neutral-500">
          위치, 색상, 재질, 가구 종류를 함께 입력해 주세요.
          <br />
          예: 이미지 중앙의 회색 패브릭 소파
        </p>
      </div>
      <label className="mt-6 block text-sm font-bold text-neutral-700">
        찾으려는 가구 설명
        <textarea
          className="mt-2 min-h-25 w-full resize-y rounded-md border border-neutral-200 bg-white p-3 text-sm font-normal outline-none focus:border-primary focus:ring-3 focus:ring-primary-50"
          maxLength={100}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="예: 이미지 중앙의 회색 패브릭 소파"
          value={description}
        />
      </label>
      {description && !isValid ? (
        <p className="mt-2 text-xs text-danger-600">
          찾으려는 가구를 2자 이상 입력해 주세요.
        </p>
      ) : null}
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Button
          fullWidth
          onClick={() => changeStage('upload')}
          startDecorator={<ArrowLeft size={17} />}
          variant="neutral-outlined"
        >
          이전으로
        </Button>
        <Button
          disabled={!isValid}
          fullWidth
          onClick={() => void redetect(description.trim())}
        >
          설명으로 재탐지
        </Button>
      </div>
    </section>
  );
};

export const SavedPanel = () => {
  const { confirmedSelections, resetWorkflow, uploadedImage } =
    useTaggingWorkflow();

  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-blue-200 bg-gradient-to-r from-blue-50 via-[#f7faff] to-white p-8 shadow-[0_12px_28px_rgba(15,23,42,0.07)]">
      <span className="flex size-14 items-center justify-center rounded-full bg-success-50 text-success-600">
        <CheckCircle2 size={28} />
      </span>
      <h2 className="mt-5 text-2xl font-extrabold text-neutral-800">
        태깅 결과가 저장되었습니다
      </h2>
      <p className="mt-2 text-sm leading-6 text-neutral-500">
        {uploadedImage?.name} · {confirmedSelections.length}개 객체
        <br />
        저장한 결과는 검수 이력에서 다시 확인할 수 있습니다.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <Link
          className="inline-flex h-10 items-center justify-center rounded-md border border-neutral-200 bg-white px-4 text-sm font-bold text-neutral-700 transition-colors hover:bg-neutral-50 hover:text-neutral-800"
          to="/history"
        >
          검수 이력 보기
        </Link>
        <Button fullWidth onClick={resetWorkflow}>
          새 이미지 태깅하기
        </Button>
      </div>
    </section>
  );
};

export const FailedPanel = () => {
  const { resetWorkflow, workflowError } = useTaggingWorkflow();

  return (
    <section className="mx-auto max-w-2xl">
      <div className="studio-surface flex min-h-75 flex-col items-center justify-center px-7 text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-warning-50 text-warning-600">
          <CircleAlert size={28} />
        </span>
        <h2 className="mt-5 text-xl font-extrabold text-neutral-800">
          가구를 찾지 못했어요
        </h2>
        <p className="mt-2 text-sm leading-6 text-neutral-500">
          {workflowError ?? '잘못된 SKU 후보는 생성하지 않았습니다.'}
          <br />
          {workflowError
            ? 'API 설정과 이미지를 확인한 뒤 다시 시도해 주세요.'
            : '가구가 더 선명하게 보이는 새 이미지로 다시 시도해 주세요.'}
        </p>
      </div>
      <Button className="mt-5" fullWidth onClick={resetWorkflow}>
        새 이미지 업로드
      </Button>
    </section>
  );
};
