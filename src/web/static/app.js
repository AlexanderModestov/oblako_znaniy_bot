// ===== Send errors to server logs =====
function logToServer(message) {
    fetch('/api/client-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
    }).catch(function () {});
}

// Catch any uncaught errors
window.onerror = function (msg, src, line) {
    logToServer('JS error: ' + msg + ' at ' + src + ':' + line);
};

// Log SDK load failures
if (window.__tgSdkFailed) logToServer('Telegram SDK failed to load');
if (window.__maxSdkFailed) logToServer('Max SDK failed to load');

// ===== Platform Detection =====
var tgWebApp = null;
var maxWebApp = null;
try { tgWebApp = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null; } catch (e) {}
try { maxWebApp = window.WebApp || null; } catch (e) {}

var isTelegram = !!(tgWebApp && tgWebApp.initData);
var isMax = !!(maxWebApp && maxWebApp.initData);

// If both have initData (shouldn't happen), prefer Telegram
if (isTelegram && isMax) {
    isMax = false;
}

if (!isTelegram && !isMax) {
    logToServer(
        'Platform not detected. '
        + 'TG SDK: ' + !!tgWebApp + ', TG initData: ' + (tgWebApp ? tgWebApp.initData.length : 'N/A') + '. '
        + 'Max SDK: ' + !!maxWebApp + ', Max initData: ' + (maxWebApp ? maxWebApp.initData.length : 'N/A') + '. '
        + 'URL: ' + window.location.href
    );
}

// ===== Platform Abstraction =====
var platform;

if (isTelegram) {
    tgWebApp.ready();
    tgWebApp.expand();
    platform = {
        name: 'telegram',
        initData: tgWebApp.initData,
        authHeader: 'X-Telegram-Init-Data',
        close: function () { tgWebApp.close(); },
        showAlert: function (msg) { tgWebApp.showAlert(msg); },
        MainButton: {
            show: function () { tgWebApp.MainButton.show(); },
            hide: function () { tgWebApp.MainButton.hide(); },
            setText: function (t) { tgWebApp.MainButton.setText(t); },
            onClick: function (cb) { tgWebApp.MainButton.onClick(cb); },
            showProgress: function () { tgWebApp.MainButton.showProgress(); },
            hideProgress: function () { tgWebApp.MainButton.hideProgress(); },
            enable: function () { tgWebApp.MainButton.enable(); },
            disable: function () { tgWebApp.MainButton.disable(); },
        },
        BackButton: {
            show: function () { tgWebApp.BackButton.show(); },
            hide: function () { tgWebApp.BackButton.hide(); },
            onClick: function (cb) { tgWebApp.BackButton.onClick(cb); },
        },
    };
} else if (isMax) {
    maxWebApp.ready();
    var $maxBtn = document.getElementById('max-main-btn');
    var maxMainCallback = null;
    $maxBtn.addEventListener('click', function () {
        if (maxMainCallback) maxMainCallback();
    });
    platform = {
        name: 'max',
        initData: maxWebApp.initData,
        authHeader: 'X-Max-Init-Data',
        close: function () { maxWebApp.close(); },
        showAlert: function (msg) {
            document.getElementById('max-alert-text').textContent = msg;
            document.getElementById('max-alert-overlay').classList.remove('hidden');
        },
        MainButton: {
            show: function () { $maxBtn.classList.remove('hidden'); },
            hide: function () { $maxBtn.classList.add('hidden'); },
            setText: function (t) { $maxBtn.textContent = t; },
            onClick: function (cb) { maxMainCallback = cb; },
            showProgress: function () { $maxBtn.textContent = '...'; $maxBtn.classList.add('disabled'); },
            hideProgress: function () { $maxBtn.classList.remove('disabled'); },
            enable: function () { $maxBtn.classList.remove('disabled'); },
            disable: function () { $maxBtn.classList.add('disabled'); },
        },
        BackButton: {
            show: function () { maxWebApp.BackButton.show(); },
            hide: function () { maxWebApp.BackButton.hide(); },
            onClick: function (cb) { maxWebApp.BackButton.onClick(cb); },
        },
    };
} else {
    // Fallback: show loading screen, user sees nothing broken
    // Error is already logged to server above
    platform = {
        name: 'unknown',
        initData: '',
        authHeader: 'X-Unknown',
        close: function () { window.close(); },
        showAlert: function (msg) {
            document.getElementById('max-alert-text').textContent = msg;
            document.getElementById('max-alert-overlay').classList.remove('hidden');
        },
        MainButton: {
            show: function () {}, hide: function () {}, setText: function () {},
            onClick: function () {}, showProgress: function () {}, hideProgress: function () {},
            enable: function () {}, disable: function () {},
        },
        BackButton: {
            show: function () {}, hide: function () {}, onClick: function () {},
        },
    };
}

var initData = platform.initData;
var urlParams = new URLSearchParams(window.location.search);
var botMessageId = urlParams.get('msg_id');
var currentStep = 0;
var formData = {
    full_name: '',
    region_id: null,
    municipality: null,
    school_id: null,
    subjects: [],
    phone: '',
    email: null,
};

// ===== DOM References =====
var $loading = document.getElementById('loading');
var $welcome = document.getElementById('welcome');
var $welcomeName = document.getElementById('welcome-name');
var $success = document.getElementById('success');
var $progressBar = document.getElementById('progress-bar');
var dots = document.querySelectorAll('.dot');

var $steps = {
    1: document.getElementById('step-1'),
    2: document.getElementById('step-2'),
    3: document.getElementById('step-3'),
    4: document.getElementById('step-4'),
    5: document.getElementById('step-5'),
    6: document.getElementById('step-6'),
    7: document.getElementById('step-7'),
};

var $inputName = document.getElementById('input-name');
var $errorName = document.getElementById('error-name');
var $searchRegion = document.getElementById('search-region');
var $listRegion = document.getElementById('list-region');
var $searchMunicipality = document.getElementById('search-municipality');
var $listMunicipality = document.getElementById('list-municipality');
var $searchSchool = document.getElementById('search-school');
var $listSchool = document.getElementById('list-school');
var $listSubjects = document.getElementById('list-subjects');
var $inputPhone = document.getElementById('input-phone');
var $errorPhone = document.getElementById('error-phone');
var $inputEmail = document.getElementById('input-email');
var $errorEmail = document.getElementById('error-email');
var $btnSkip = document.getElementById('btn-skip');

// Municipality data cached from API
var municipalitiesData = [];

// ===== API Helper =====
async function api(method, url, body) {
    var headers = { 'Content-Type': 'application/json' };
    headers[platform.authHeader] = initData;
    var opts = { method: method, headers: headers };
    if (body !== undefined && body !== null) {
        opts.body = JSON.stringify(body);
    }
    var res = await fetch(url, opts);
    if (!res.ok) {
        var text = await res.text().catch(function () { return ''; });
        throw new Error('API error: ' + res.status + ' ' + text);
    }
    return res.json();
}

// ===== Debounce =====
function debounce(fn, ms) {
    var timer = null;
    return function () {
        var args = arguments;
        var ctx = this;
        clearTimeout(timer);
        timer = setTimeout(function () {
            fn.apply(ctx, args);
        }, ms);
    };
}

// ===== Screen Management =====
function hideAll() {
    $loading.classList.add('hidden');
    $welcome.classList.add('hidden');
    $success.classList.add('hidden');
    $progressBar.classList.add('hidden');
    for (var i = 1; i <= 7; i++) {
        $steps[i].classList.remove('active');
    }
}

function showScreen(id) {
    hideAll();
    document.getElementById(id).classList.remove('hidden');
    platform.MainButton.hide();
    platform.BackButton.hide();
}

// ===== Progress Dots =====
function updateProgress(step) {
    dots.forEach(function (dot) {
        var s = parseInt(dot.getAttribute('data-step'), 10);
        dot.classList.remove('active', 'completed');
        if (s < step) {
            dot.classList.add('completed');
        } else if (s === step) {
            dot.classList.add('active');
        }
    });
}

// ===== Show Step =====
function showStep(n) {
    hideAll();
    currentStep = n;
    $progressBar.classList.remove('hidden');
    $steps[n].classList.add('active');
    updateProgress(n);

    // BackButton
    if (n > 1) {
        platform.BackButton.show();
    } else {
        platform.BackButton.hide();
    }

    // MainButton configuration per step
    if (n === 1) {
        platform.MainButton.setText('Далее');
        platform.MainButton.show();
    } else if (n === 2 || n === 3 || n === 4) {
        platform.MainButton.hide();
    } else if (n === 5) {
        platform.MainButton.setText('Готово');
        if (formData.subjects.length > 0) {
            platform.MainButton.show();
        } else {
            platform.MainButton.hide();
        }
    } else if (n === 6) {
        platform.MainButton.setText('Далее');
        platform.MainButton.show();
    } else if (n === 7) {
        platform.MainButton.setText('Готово');
        platform.MainButton.show();
    }

    // Trigger data loading for certain steps
    if (n === 2) {
        $searchRegion.value = '';
        loadRegions('');
    } else if (n === 3) {
        $searchMunicipality.value = '';
        loadMunicipalities('');
    } else if (n === 4) {
        $searchSchool.value = '';
        loadSchools('');
    } else if (n === 5) {
        loadSubjects();
    }
}

// ===== Step 1: ФИО =====
function validateName() {
    var val = $inputName.value.trim();
    if (val.split(/\s+/).length < 3) {
        $errorName.textContent = 'Введите фамилию, имя и отчество (3 слова)';
        return false;
    }
    $errorName.textContent = '';
    return true;
}

function handleStep1() {
    if (!validateName()) return;
    formData.full_name = $inputName.value.trim();
    showStep(2);
}

// ===== Step 2: Regions =====
function renderList(container, items, onSelect) {
    container.innerHTML = '';
    if (items.length === 0) {
        var empty = document.createElement('div');
        empty.className = 'list-empty';
        empty.textContent = 'Ничего не найдено';
        container.appendChild(empty);
        return;
    }
    items.forEach(function (item) {
        var el = document.createElement('button');
        el.className = 'list-item';
        el.textContent = item.name;
        el.addEventListener('click', function () {
            onSelect(item);
        });
        container.appendChild(el);
    });
}

async function loadRegions(query) {
    try {
        var url = '/api/regions';
        if (query) url += '?q=' + encodeURIComponent(query);
        var data = await api('GET', url);
        renderList($listRegion, data, function (item) {
            formData.region_id = item.id;
            showStep(3);
        });
    } catch (err) {
        $listRegion.innerHTML = '<div class="list-empty">Ошибка загрузки. Попробуйте ещё раз.</div>';
    }
}

var debouncedRegionSearch = debounce(function () {
    loadRegions($searchRegion.value.trim());
}, 300);

$searchRegion.addEventListener('input', debouncedRegionSearch);

// ===== Step 3: Municipalities =====
async function loadMunicipalities(query) {
    try {
        var url = '/api/municipalities/' + formData.region_id;
        var data = await api('GET', url);
        municipalitiesData = data;
        var filtered = data;
        if (query) {
            var q = query.toLowerCase();
            filtered = data.filter(function (item) {
                return item.name.toLowerCase().indexOf(q) !== -1;
            });
        }
        if (filtered.length === 0 && !query) {
            showStep(4);
            return;
        }
        renderList($listMunicipality, filtered, function (item) {
            formData.municipality = item.name;
            showStep(4);
        });
    } catch (err) {
        $listMunicipality.innerHTML = '<div class="list-empty">Ошибка загрузки. Попробуйте ещё раз.</div>';
    }
}

var debouncedMunicipalitySearch = debounce(function () {
    var query = $searchMunicipality.value.trim();
    if (municipalitiesData.length > 0) {
        var filtered = municipalitiesData;
        if (query) {
            var q = query.toLowerCase();
            filtered = municipalitiesData.filter(function (item) {
                return item.name.toLowerCase().indexOf(q) !== -1;
            });
        }
        renderList($listMunicipality, filtered, function (item) {
            formData.municipality = item.name;
            showStep(4);
        });
    } else {
        loadMunicipalities(query);
    }
}, 300);

$searchMunicipality.addEventListener('input', debouncedMunicipalitySearch);

// ===== Step 4: Schools =====
async function loadSchools(query) {
    try {
        var url = '/api/schools/' + formData.region_id;
        if (query) url += '?q=' + encodeURIComponent(query);
        if (!query && formData.municipality) url += '?municipality=' + encodeURIComponent(formData.municipality);
        var data = await api('GET', url);
        renderList($listSchool, data, function (item) {
            formData.school_id = item.id;
            showStep(5);
        });
    } catch (err) {
        $listSchool.innerHTML = '<div class="list-empty">Ошибка загрузки. Попробуйте ещё раз.</div>';
    }
}

var debouncedSchoolSearch = debounce(function () {
    loadSchools($searchSchool.value.trim());
}, 300);

$searchSchool.addEventListener('input', debouncedSchoolSearch);

// ===== Step 5: Subjects =====
var subjectsLoaded = false;

async function loadSubjects() {
    if (subjectsLoaded) {
        updateSubjectSelection();
        return;
    }
    try {
        var data = await api('GET', '/api/subjects');
        $listSubjects.innerHTML = '';
        data.forEach(function (item) {
            var card = document.createElement('button');
            card.className = 'subject-card';
            card.setAttribute('data-id', item.id);

            var checkIcon = document.createElement('span');
            checkIcon.className = 'check-icon';
            checkIcon.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6L5 9L10 3" stroke="var(--tg-theme-button-color, #3390ec)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

            var label = document.createElement('span');
            label.textContent = item.name;

            card.appendChild(checkIcon);
            card.appendChild(label);

            card.addEventListener('click', function () {
                toggleSubject(item.id, card);
            });

            $listSubjects.appendChild(card);
        });
        subjectsLoaded = true;
    } catch (err) {
        $listSubjects.innerHTML = '<div class="list-empty">Ошибка загрузки. Попробуйте ещё раз.</div>';
    }
}

function toggleSubject(id, card) {
    var idx = formData.subjects.indexOf(id);
    if (idx === -1) {
        formData.subjects.push(id);
        card.classList.add('selected');
    } else {
        formData.subjects.splice(idx, 1);
        card.classList.remove('selected');
    }
    if (formData.subjects.length > 0) {
        platform.MainButton.show();
    } else {
        platform.MainButton.hide();
    }
}

function updateSubjectSelection() {
    var cards = $listSubjects.querySelectorAll('.subject-card');
    cards.forEach(function (card) {
        var id = parseInt(card.getAttribute('data-id'), 10);
        if (formData.subjects.indexOf(id) !== -1) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });
    if (formData.subjects.length > 0) {
        platform.MainButton.show();
    } else {
        platform.MainButton.hide();
    }
}

function handleStep5() {
    if (formData.subjects.length === 0) return;
    showStep(6);
}

// ===== Step 6: Phone =====
function validatePhone() {
    var val = $inputPhone.value.trim().replace(/[\s\-\(\)]/g, '');
    if (!/^\+7\d{10}$/.test(val)) {
        $errorPhone.textContent = 'Введите номер в формате +7XXXXXXXXXX';
        return false;
    }
    $errorPhone.textContent = '';
    return true;
}

function handleStep6() {
    if (!validatePhone()) return;
    formData.phone = $inputPhone.value.trim();
    showStep(7);
}

// ===== Step 7: Email =====
function validateEmail() {
    var val = $inputEmail.value.trim();
    if (val && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        $errorEmail.textContent = 'Введите корректный email';
        return false;
    }
    $errorEmail.textContent = '';
    return true;
}

function handleStep7() {
    if (!validateEmail()) return;
    var val = $inputEmail.value.trim();
    formData.email = val || null;
    submitRegistration();
}

$btnSkip.addEventListener('click', function () {
    formData.email = null;
    submitRegistration();
});

// ===== Submit =====
async function submitRegistration() {
    platform.MainButton.showProgress();
    platform.MainButton.disable();
    try {
        var registerUrl = '/api/register';
        if (botMessageId) registerUrl += '?bot_msg_id=' + botMessageId;
        await api('POST', registerUrl, {
            telegram_id: 0,
            full_name: formData.full_name,
            region_id: formData.region_id,
            school_id: formData.school_id,
            subjects: formData.subjects,
            phone: formData.phone,
            email: formData.email,
        });
        platform.MainButton.hideProgress();
        platform.MainButton.hide();
        platform.BackButton.hide();
        hideAll();
        $success.classList.remove('hidden');
        setTimeout(function () {
            platform.close();
        }, 2000);
    } catch (err) {
        platform.MainButton.hideProgress();
        platform.MainButton.enable();
        platform.showAlert('Ошибка при регистрации. Попробуйте ещё раз.');
    }
}

// ===== MainButton Handler =====
function handleMainButton() {
    switch (currentStep) {
        case 1: handleStep1(); break;
        case 5: handleStep5(); break;
        case 6: handleStep6(); break;
        case 7: handleStep7(); break;
    }
}

platform.MainButton.onClick(handleMainButton);

// ===== BackButton Handler =====
function handleBack() {
    if (currentStep > 1) {
        if (currentStep === 4 && municipalitiesData.length === 0) {
            showStep(2);
        } else {
            showStep(currentStep - 1);
        }
    }
}

platform.BackButton.onClick(handleBack);

// ===== Init =====
async function init() {
    showScreen('loading');
    try {
        var result = await api('POST', '/api/auth');
        if (result.status === 'existing') {
            hideAll();
            $welcomeName.textContent = result.full_name || '';
            $welcome.classList.remove('hidden');
            platform.MainButton.hide();
            platform.BackButton.hide();
        } else {
            showStep(1);
        }
    } catch (err) {
        logToServer('Auth failed: ' + err.message + ' | platform: ' + platform.name + ' | initData length: ' + initData.length);
        platform.showAlert('Не удалось загрузить приложение. Попробуйте открыть заново.');
    }
}

init();
