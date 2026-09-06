// Powers the live translate form (no page reload).
document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('translate-form');
    if (!form) return;

    form.addEventListener('submit', function (event) {
        event.preventDefault();

        var text = document.getElementById('text').value;
        var source = document.getElementById('source').value;
        var target = document.getElementById('target').value;
        var resultBox = document.getElementById('result-text');

        resultBox.textContent = 'Translating...';

        fetch(form.action || window.location.pathname, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, source: source, target: target }),
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { status: response.status, data: data };
                });
            })
            .then(function (result) {
                if (result.status === 200) {
                    resultBox.textContent = result.data.translated_text;
                } else {
                    resultBox.textContent = result.data.error || 'Something went wrong.';
                }
            })
            .catch(function () {
                resultBox.textContent = 'Could not reach the server. Please try again.';
            });
    });
});
