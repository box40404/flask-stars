const starButtons = document.querySelectorAll('.star-btn');
const starInput = document.getElementById('starInput');
const priceSpan = document.getElementById('price');
const buyButton = document.querySelector('.buy-btn');

// Текущее выбранное количество
let currentAmount = 50;


// Обновление текста
function updateText(amount) {
    // const price = starPrices[amount] || Math.round(amount * 258.02);
    // priceSpan.textContent = price.toLocaleString('ru-RU');
    
    const switchBtn = document.querySelector('.switch-btn');
    const isTon = switchBtn.classList.contains('on');
    buyButton.innerHTML = `Купить ${amount} ${isTon ? 'TON' : 'звезд'}`;
    updateIcons(isTon); // Обновляем иконки
    
}

// Обновление иконок в зависимости от валюты
function updateIcons(isTon) {
    const iconPath = isTon ? '/static/img/Vector(14).svg' : '/static/img/Vector(12).svg';
    starButtons.forEach(button => {
        const img = button.querySelector('img');
        if (img) {
            img.src = iconPath;
            img.alt = isTon ? 'TON' : 'Star';

        }
    });
}

// Обработчики кликов по кнопкам выбора количества
starButtons.forEach(button => {
    button.addEventListener('click', () => {
        starButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        const amount = parseInt(button.dataset.amount);
        currentAmount = amount;
        starInput.value = amount;
        updateText(amount)
    });
});

// Обработчик изменения поля ввода
starInput.addEventListener('input', (e) => {
    const amount = parseInt(e.target.value) || 0;
    if (amount > 0) {
        currentAmount = amount;
        const matchingButton = document.querySelector(`[data-amount="${amount}"]`);
        starButtons.forEach(btn => btn.classList.remove('active'));
        if (matchingButton) {
            matchingButton.classList.add('active');
        }
    }
    updateText(amount)
});


// Обработчик переключателя
// let isOn = false;
// function toggleSwitch() {
//     isOn = !isOn;
//     const switchBtn = document.querySelector('.switch-btn');
//     switchBtn.classList.toggle('on', isOn); // Переключаем класс
//     updatePriceAndText(currentAmount); // Обновляем текст кнопки
//     const slider = switchBtn.querySelector('.slider');
//     if (isOn) {
//         console.log("Switched to TON");
//     } else {
//         console.log("Switched to Star");
//     }
//     // Двигаем слайдер через CSS-класс, а не напрямую
// }


// Обработчики чекбоксов
const checkboxes = document.querySelectorAll('.checkbox');
checkboxes.forEach(checkbox => {
    checkbox.addEventListener('change', (e) => {
        console.log(`Чекбокс ${e.target.nextElementSibling.textContent.trim()} ${e.target.checked ? 'отмечен' : 'снят'}`);
    });
});

// Анимация появления элементов при скролле
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Применяем анимацию к карточкам и секциям
document.querySelectorAll('.feature-card, .stat-item, .stats-banner').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    starInput.value = currentAmount;
    const switchBtn = document.querySelector('.switch-btn');
    // switchBtn.addEventListener('click', toggleSwitch); // Привязываем обработчик
    // updateIcons(false); // Инициализируем иконки для начального состояния (Star)
});