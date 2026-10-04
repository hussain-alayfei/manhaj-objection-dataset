"""Model-provider configuration shared by diagnosis, embeddings, and extraction.

Nothing here contacts a provider at import time; clients are built lazily so a
missing key degrades to an explicit abstention instead of a crash.
"""
import os


def llm_provider():
    explicit = os.getenv('LLM_PROVIDER', '').strip().lower()
    if explicit: return explicit
    # Backwards compatible: a configured local model name meant Ollama.
    return 'ollama' if os.getenv('DIAGNOSIS_MODEL') else 'none'


def embedding_provider():
    return os.getenv('EMBEDDING_PROVIDER', 'ollama').strip().lower()


def embedding_dim():
    return int(os.getenv('EMBEDDING_DIM', '768'))


def openai_client(timeout=120, max_retries=1):
    if not os.getenv('OPENAI_API_KEY'): raise ValueError('OPENAI_API_KEY is not configured')
    from openai import OpenAI
    return OpenAI(timeout=timeout, max_retries=max_retries)


def provider_errors():
    """Exception types that mean 'provider unavailable or refused'; callers abstain on these."""
    import httpx
    errors = [httpx.HTTPError, ValueError]
    try:
        from openai import OpenAIError
        errors.append(OpenAIError)
    except ImportError:
        pass
    return tuple(errors)


def validate_config():
    """Fail fast on contradictory provider settings instead of silently abstaining forever."""
    problems = []
    if llm_provider() == 'openai' and not os.getenv('OPENAI_API_KEY'): problems.append('LLM_PROVIDER=openai requires OPENAI_API_KEY')
    if llm_provider() == 'openai' and not os.getenv('DIAGNOSIS_MODEL'): problems.append('LLM_PROVIDER=openai requires DIAGNOSIS_MODEL')
    if llm_provider() not in ('openai', 'ollama', 'none'): problems.append('LLM_PROVIDER must be openai, ollama, or none')
    if os.getenv('EMBEDDING_MODEL'):
        if embedding_provider() not in ('openai', 'ollama', 'sentence_transformers'): problems.append('Unsupported EMBEDDING_PROVIDER')
        if embedding_provider() == 'openai' and not os.getenv('OPENAI_API_KEY'): problems.append('EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY')
    if problems: raise RuntimeError('; '.join(problems))
