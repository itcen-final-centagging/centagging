"""임베딩 CLI 환경 변수 우선순위 테스트입니다."""

import unittest.mock

from scripts.embedding import storage


def test_shell_environment_overrides_dotenv_for_host_execution() -> None:
    """호스트에서 지정한 POSTGRES_HOST가 .env의 Docker 별칭보다 우선한다."""
    with unittest.mock.patch.object(storage, "load_dotenv") as load_dotenv:
        storage.load_environment()

    assert load_dotenv.call_args.kwargs["override"] is False
