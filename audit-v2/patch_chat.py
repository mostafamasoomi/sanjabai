import re
p="/root/multiai/backend/chat.py"
s=open(p).read()

# Add resilience guard: wrap _select_smart_model body so any non-reliable pick falls back
old_sig="def _select_smart_model(category: str, balance: int, plan: str) -> tuple[str, str]:\n"
assert old_sig in s, "signature not found"
# Replace the final two lines '    return _DEFAULT_MODEL\n\n\n@router.post' section:
# We add a guard right before the final return by renaming. Simplest: insert a check after function returns via wrapper.
# Instead, replace the trailing return with a validated one using a local capture is complex; add a module-level helper and re-route final returns.
# Easiest robust approach: append a guarded wrapper that post-checks.
guard = '''
def _select_smart_model_safe(category: str, balance: int, plan: str) -> tuple[str, str]:
    model, provider = _select_smart_model(category, balance, plan)
    if model not in _RELIABLE_MODELS:
        return _DEFAULT_MODEL
    return model, provider

'''
# swap callers: replace calls to _select_smart_model( with _select_smart_model_safe(
s2 = s.replace("_select_smart_model(category, balance, plan)", "_select_smart_model_safe(category, balance, plan)")
assert s2 != s, "no caller replaced"
# insert the wrapper right after the original function (before the @router.post decorator)
anchor = "@router.post('/v1/smart-chat')"
assert anchor in s2
s3 = s2.replace(anchor, guard + anchor, 1)
open(p,"w").write(s3)
print("patched OK; safe wrapper added")
