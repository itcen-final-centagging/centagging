import { useState, type FormEvent } from 'react';
import { LogIn } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/commons/components/Button';
import { useAuth } from '@/features/auth/hooks/useAuth';

const SESSION_EXPIRED_MESSAGE =
  '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해 주세요.';

export const LoginPage = () => {
  const navigate = useNavigate();
  const { authError, login } = useAuth();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState<string>();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(undefined);
    setIsSubmitting(true);

    try {
      await login({ loginId, password });
      navigate('/', { replace: true });
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : '로그인 요청을 처리하지 못했습니다.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const displayedError =
    errorMessage ??
    (authError === 'expired_session' ? SESSION_EXPIRED_MESSAGE : undefined);

  return (
    <main className="studio-content-gradient flex min-h-screen items-center justify-center px-5 py-10">
      <section
        aria-labelledby="login-title"
        className="w-full max-w-md rounded-2xl border border-border bg-bg-primary p-8 shadow-[0_20px_45px_rgba(15,23,42,0.12)] sm:p-10"
      >
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-blue-700 text-white">
            <LogIn aria-hidden="true" size={23} />
          </div>
          <p className="mb-2 text-sm font-semibold text-blue-700">CenTagging</p>
          <h1 className="text-2xl font-bold text-text-primary" id="login-title">
            로그인
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            계정 정보를 입력해 태깅 작업을 시작하세요.
          </p>
        </div>

        {displayedError ? (
          <p
            aria-live="polite"
            className="mb-5 rounded-lg border border-danger-200 bg-danger-20 px-3 py-2.5 text-sm text-danger-600"
            role="alert"
          >
            {displayedError}
          </p>
        ) : null}

        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-semibold text-text-primary">
            아이디
            <input
              autoComplete="username"
              className="mt-2 h-11 w-full rounded-lg border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-quaternary focus:border-blue-500"
              name="loginId"
              onChange={(event) => setLoginId(event.target.value)}
              placeholder="아이디를 입력하세요"
              required
              value={loginId}
            />
          </label>
          <label className="block text-sm font-semibold text-text-primary">
            비밀번호
            <input
              autoComplete="current-password"
              className="mt-2 h-11 w-full rounded-lg border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-quaternary focus:border-blue-500"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="비밀번호를 입력하세요"
              required
              type="password"
              value={password}
            />
          </label>
          <Button disabled={isSubmitting} fullWidth size="lg" type="submit">
            {isSubmitting ? '로그인 중...' : '로그인'}
          </Button>
        </form>
      </section>
    </main>
  );
};
