const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const initData = tg.initData;
const urlParams = new URLSearchParams(window.location.search);
const botMessageId = urlParams.get('msg_id');
let currentStep = 0;
const formData = {
    full_name: '',
    region_id: null,
    school_id: null,
    subjects: [],
    phone: '',
    email: null,
};

// ===== DOM References =====
const $loading = document.getElementById('loading');
const $welcome = document.getElementById('welcome');
const $welcomeName = document.getElementById('welcome-name');
const $success = document.getElementById('success');
const $progressBar = document.getElementById('progress-bar');
const dots = document.querySelectorAll('.dot');

const $steps = {
    1: document.getElementById('step-1'),
    2: document.getElementById('step-2'),
    3: document.getElementById('step-3'),
    4: document.getElementById('step-4'),
    5: document.getElementById('step-5'),
    6: document.getElementById('step-6'),
};

const $inputName = document.getElementById('input-name');
const $errorName = document.getElementById('error-name');
const $searchRegion = document.getElementById('search-region');
const $listRegion = document.getElementById('list-region');
const $searchSchool = document.getElementById('search-school');
const $listSchool = document.getElementById('list-school');
const $listSubjects = document.getElementById('list-subjects');
const $inputPhone = document.getElementById('input-phone');
const $errorPhone = document.getElementById('error-phone');
const $inputEmail = document.getElementById('input-email');
const $errorEmail = document.getElementById('error-email');
const $btnSkip = document.getElementById('btn-skip');

// ===== API Helper =====
async function api(method, url, body) {
    const opts = {
        method,
        headers: {
            'X-Telegram-Init-Data': initData,
            'Content-Type': 'application/json',
        },
    };
    if (body !== undefined && body !== null) {
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error('API error: ' + res.status + ' ' + text);
    }
    return res.json();
}

// ===== Debounce =====
function debounce(fn, ms) {
    let timer = null;
    return function () {
        const args = arguments;
        const ctx = this;
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
    for (let i = 1; i <= 6; i++) {
        $steps[i].classList.remove('active');
    }
}

function showScreen(id) {
    hideAll();
    document.getElementById(id).classList.remove('hidden');
    tg.MainButton.hide();
    tg.BackButton.hide();
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
        tg.BackButton.show();
    } else {
        tg.BackButton.hide();
    }

    // MainButton configuration per step
    if (n === 1) {
        tg.MainButton.setText('Далее');
        tg.MainButton.show();
    } else if (n === 2 || n === 3) {
        // Selection-based, no MainButton
        tg.MainButton.hide();
    } else if (n === 4) {
        tg.MainButton.setText('Готово');
        // Show only if at least 1 subject selected
        if (formData.subjects.length > 0) {
            tg.MainButton.show();
        } else {
            tg.MainButton.hide();
        }
    } else if (n === 5) {
        tg.MainButton.setText('Далее');
        tg.MainButton.show();
    } else if (n === 6) {
        tg.MainButton.setText('Готово');
        tg.MainButton.show();
    }

    // Trigger data loading for certain steps
    if (n === 2) {
        $searchRegion.value = '';
        loadRegions('');
    } else if (n === 3) {
        $searchSchool.value = '';
        loadSchools('');
    } else if (n === 4) {
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

// ===== Step 3: Schools =====
async function loadSchools(query) {
    try {
        var url = '/api/schools/' + formData.region_id;
        if (query) url += '?q=' + encodeURIComponent(query);
        var data = await api('GET', url);
        renderList($listSchool, data, function (item) {
            formData.school_id = item.id;
            showStep(4);
        });
    } catch (err) {
        $listSchool.innerHTML = '<div class="list-empty">Ошибка загрузки. Попробуйте ещё раз.</div>';
    }
}

var debouncedSchoolSearch = debounce(function () {
    loadSchools($searchSchool.value.trim());
}, 300);

$searchSchool.addEventListener('input', debouncedSchoolSearch);

// ===== Step 4: Subjects =====
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
    // Show/hide MainButton based on selection count
    if (formData.subjects.length > 0) {
        tg.MainButton.show();
    } else {
        tg.MainButton.hide();
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
        tg.MainButton.show();
    } else {
        tg.MainButton.hide();
    }
}

function handleStep4() {
    if (formData.subjects.length === 0) return;
    showStep(5);
}

// ===== Step 5: Phone =====
function validatePhone() {
    var val = $inputPhone.value.trim().replace(/[\s\-\(\)]/g, '');
    if (!/^\+7\d{10}$/.test(val)) {
        $errorPhone.textContent = 'Введите номер в формате +7XXXXXXXXXX';
        return false;
    }
    $errorPhone.textContent = '';
    return true;
}

function handleStep5() {
    if (!validatePhone()) return;
    formData.phone = $inputPhone.value.trim();
    showStep(6);
}

// ===== Step 6: Email =====
function validateEmail() {
    var val = $inputEmail.value.trim();
    if (val && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        $errorEmail.textContent = 'Введите корректный email';
        return false;
    }
    $errorEmail.textContent = '';
    return true;
}

function handleStep6() {
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
    tg.MainButton.showProgress();
    tg.MainButton.disable();
    try {
        var registerUrl = '/api/register';
        if (botMessageId) registerUrl += '?bot_msg_id=' + botMessageId;
        await api('POST', registerUrl, {
            telegram_id: 0,  // Will be overridden by server from auth header
            full_name: formData.full_name,
            region_id: formData.region_id,
            school_id: formData.school_id,
            subjects: formData.subjects,
            phone: formData.phone,
            email: formData.email,
        });
        tg.MainButton.hideProgress();
        tg.MainButton.hide();
        tg.BackButton.hide();
        hideAll();
        $success.classList.remove('hidden');
        setTimeout(function () {
            tg.close();
        }, 2000);
    } catch (err) {
        tg.MainButton.hideProgress();
        tg.MainButton.enable();
        tg.showAlert('Ошибка при регистрации. Попробуйте ещё раз.');
    }
}

// ===== MainButton Handler =====
function handleMainButton() {
    switch (currentStep) {
        case 1: handleStep1(); break;
        case 4: handleStep4(); break;
        case 5: handleStep5(); break;
        case 6: handleStep6(); break;
    }
}

tg.MainButton.onClick(handleMainButton);

// ===== BackButton Handler =====
function handleBack() {
    if (currentStep > 1) {
        showStep(currentStep - 1);
    }
}

tg.BackButton.onClick(handleBack);

// ===== Init =====
async function init() {
    showScreen('loading');
    try {
        var result = await api('POST', '/api/auth');
        if (result.status === 'existing') {
            hideAll();
            $welcomeName.textContent = result.full_name || '';
            $welcome.classList.remove('hidden');
            tg.MainButton.hide();
            tg.BackButton.hide();
        } else {
            showStep(1);
        }
    } catch (err) {
        hideAll();
        $loading.classList.remove('hidden');
        tg.showAlert('Ошибка инициализации. Попробуйте открыть приложение заново.');
    }
}

init();
