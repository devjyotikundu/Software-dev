import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Curated list of common languages for the dropdowns. Codes match what
# deep-translator's GoogleTranslator expects.
LANGUAGES = {
    'auto': 'Detect language',
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'hi': 'Hindi',
    'bn': 'Bengali',
    'ru': 'Russian',
    'zh-CN': 'Chinese (Simplified)',
    'ja': 'Japanese',
    'ko': 'Korean',
    'ar': 'Arabic',
    'pt': 'Portuguese',
    'it': 'Italian',
    'ta': 'Tamil',
    'te': 'Telugu',
}


def _wants_json(request):
    return request.content_type == 'application/json'


def _do_translate(text, source, target):
    """
    Wraps deep-translator so a network hiccup becomes a clear error message
    instead of a crash (DoD: "expected browser and server errors are
    handled clearly").
    """
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source or 'auto', target=target).translate(text)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def translate_view(request):
    """
    GET  -> render the public translate page (no login required)
    POST /translate/
    Given: text + source/target languages, no login
    Then: 200 with translated text
    """
    if request.method == 'GET':
        return render(request, 'translator/translate.html', {'languages': LANGUAGES})

    if _wants_json(request):
        data = json.loads(request.body or '{}')
    else:
        data = request.POST

    text = (data.get('text') or '').strip()
    source = data.get('source', 'auto')
    target = data.get('target', 'en')

    if not text:
        error = 'Please enter some text to translate.'
        if _wants_json(request):
            return JsonResponse({'error': error}, status=400)
        return render(request, 'translator/translate.html', {
            'languages': LANGUAGES, 'error': error, 'text': text, 'source': source, 'target': target,
        })

    try:
        translated = _do_translate(text, source, target)
    except Exception:
        error = 'Translation service is unavailable right now. Please try again in a moment.'
        if _wants_json(request):
            return JsonResponse({'error': error}, status=502)
        return render(request, 'translator/translate.html', {
            'languages': LANGUAGES, 'error': error, 'text': text, 'source': source, 'target': target,
        })

    if _wants_json(request):
        return JsonResponse({'translated_text': translated}, status=200)
    return render(request, 'translator/translate.html', {
        'languages': LANGUAGES, 'translated_text': translated,
        'text': text, 'source': source, 'target': target,
    })
