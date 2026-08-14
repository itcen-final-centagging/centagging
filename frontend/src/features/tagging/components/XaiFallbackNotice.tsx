import { AlertTriangle } from 'lucide-react';

import type { XaiFallbackReason, XaiStatus } from '@/features/tagging/types';

const fallbackMessages: Record<XaiFallbackReason, string> = {
  PROCESSING_ERROR:
    'XAI 분석 중 오류가 발생했습니다. 현재 후보는 이미지 유사도 기준으로 제공됩니다.',
  RATE_LIMITED:
    'Gemini 요청 한도를 초과해 XAI 분석을 완료하지 못했습니다. 현재 후보는 이미지 유사도 기준으로 제공됩니다.',
  UNAVAILABLE:
    'XAI 분석에 필요한 후보 이미지를 확인하지 못했습니다. 현재 후보는 이미지 유사도 기준으로 제공됩니다.',
};

interface XaiFallbackNoticeProps {
  reason: XaiFallbackReason | null;
  status: XaiStatus | null;
}

export const XaiFallbackNotice = ({
  reason,
  status,
}: XaiFallbackNoticeProps) => {
  if (status !== 'FALLBACK' || reason === null) return null;

  return (
    <div
      className="flex gap-3 rounded-xl border border-warning-200 bg-warning-50 px-4 py-3 text-warning-700"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 shrink-0" size={18} />
      <div>
        <p className="text-sm font-bold">XAI 분석 폴백</p>
        <p className="mt-1 text-xs leading-5">{fallbackMessages[reason]}</p>
      </div>
    </div>
  );
};
