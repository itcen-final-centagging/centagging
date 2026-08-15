import type React from 'react';
import { Clock3, Plus, Tag } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';

export const HistoryPage: React.FC = () => {
  const { history, historyError, resetWorkflow } = useTaggingWorkflow();

  return (
    <div className="px-6 py-6 pb-10">
      <div className="flex items-center gap-2">
        <span className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
          가구 태깅
        </span>
        <span className="text-text-secondary">/</span>
        <h1 className="studio-page-title text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
          검수 이력
        </h1>
      </div>
      <p className="mt-1 text-sm leading-6 text-text-secondary">
        저장된 상품 연결과 태깅 결과를 최신순으로 확인합니다.
      </p>
      {historyError ? (
        <p
          className="mt-6 rounded-md border border-warning-200 bg-warning-50 px-4 py-3 text-sm font-semibold text-warning-700"
          role="alert"
        >
          최신 이력을 불러오지 못했습니다. {historyError}
        </p>
      ) : null}
      {history.length === 0 && !historyError ? (
        <section className="studio-surface mt-6 flex min-h-90 flex-col items-center justify-center px-6 text-center">
          <span className="flex size-16 items-center justify-center rounded-full bg-blue-100 text-blue-700">
            <Clock3 size={28} />
          </span>
          <h2 className="mt-5 text-xl font-bold text-text-primary">
            저장된 검수 이력이 없습니다
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            새 태깅 작업에서 SKU와 태그를 검수한 후 저장해 주세요.
          </p>
          <Link
            className="mt-5 inline-flex min-h-[42px] items-center justify-center gap-2 rounded-xl border border-blue-700 bg-blue-700 px-[18px] text-sm font-semibold text-white transition-all hover:-translate-y-px hover:border-blue-900 hover:bg-blue-900"
            onClick={resetWorkflow}
            to="/"
          >
            <Plus size={17} />새 태깅 작업
          </Link>
        </section>
      ) : null}
      {history.length > 0 ? (
        <section className="mt-6 max-w-4xl">
          <p className="mb-3 text-sm font-bold text-text-primary">
            저장된 작업{' '}
            <span className="rounded-full bg-success-50 px-2 py-1 text-xs text-success-600">
              {history.length}건
            </span>
          </p>
          <div className="space-y-3">
            {history.map((record) => (
              <article
                className="studio-surface studio-panel-hover p-5"
                key={record.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-primary">
                    {record.sku}
                  </span>
                  <span className="text-xs text-neutral-400">
                    {record.savedAt}
                  </span>
                </div>
                <h2 className="mt-2 text-base font-extrabold text-neutral-800">
                  {record.productName}
                </h2>
                <p className="mt-1.5 text-sm text-neutral-500">
                  {record.objectName} · {record.imageName}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {record.tags.styleTags.map((tag) => (
                    <span
                      className="inline-flex items-center gap-1 rounded-full bg-primary-20 px-2.5 py-1.5 text-xs font-bold text-primary-700"
                      key={tag}
                    >
                      <Tag size={12} />
                      {tag}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
};
