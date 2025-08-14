const userInput = document.getElementById('usernameInput');
const quantityInput2 = document.getElementById('quantityInput');
const currencySelect = document.getElementById('currencySelect');
const costOutput = document.getElementById('costOutput');
const currencyOutput = document.getElementById('currencyOutput');
const statusDisplay = document.querySelector('.status-display');
const statusOutput = document.getElementById('statusOutput');
const buyBtn = document.getElementById('buyButton');
const buyButtonStars = document.getElementById('buyButtonStars');
const starsOptions = document.querySelectorAll('input[name="stars"]');
const notification = document.createElement('div');
document.body.appendChild(notification);
notification.id = 'notification';
notification.style.position = 'fixed';
notification.style.top = '20px';
notification.style.right = '20px';
notification.style.padding = '15px';
notification.style.borderRadius = '5px';
notification.style.color = 'white';
notification.style.display = 'none';
notification.style.zIndex = '1000';

let prices = {};
let purchaseId = null;

// Функция отображения уведомлений
function showNotification(message, type) {
    notification.textContent = message;
    notification.className = type;
    notification.style.backgroundColor = type === 'success' ? '#28a745' : '#dc3545';
    notification.style.display = 'block';
    setTimeout(() => {
        notification.style.display = 'none';
    }, 5000);
}

// Функция обновления стоимости
function updatePrice() {
    const amount = Number(quantityInput2.value) || 50;
    const currency = currencySelect.value;
    // Обновляем цены с учетом текущего количества звезд
    fetch('/api/prices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            initData: window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp.initData : null,
            user_id: localStorage.getItem("telegram_user_id") || null,
            amount: amount
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification(`Ошибка загрузки цен: ${data.error}`, 'error');
                return;
            }
            prices = data;
            costOutput.textContent = prices[currency] ? prices[currency].discounted.toFixed(6) : '0';
            currencyOutput.textContent = currency;
            buyButtonStars.textContent = amount;
            buyBtn.textContent = `Купить ${amount} звёзд`;
        })
        .catch(() => showNotification('Ошибка загрузки цен', 'error'));
}

// Проверка Telegram Web App
if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    const initData = window.Telegram.WebApp.initData;
    if (initData) {
        localStorage.clear();
        fetch('/api/verify-init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData })
        })
            .then(response => response.json())
            .then(data => {
                if (data.user_id) {
                    localStorage.setItem("telegram_user_id", data.user_id);
                    userInput.value = `@${data.username}`;
                    updatePrice();
                } else {
                    showNotification(`Ошибка авторизации: ${data.error}`, 'error');
                    updatePrice();
                }
            })
            .catch(() => {
                showNotification('Ошибка сервера при проверке авторизации', 'error');
                updatePrice();
            });
    }
} else {
    // Для браузера загружаем цены без initData
    updatePrice();
    // Восстанавливаем состояние из localStorage
    const savedPurchaseId = localStorage.getItem('purchase_id');
    if (savedPurchaseId) {
        purchaseId = savedPurchaseId;
        quantityInput2.value = localStorage.getItem('amount') || '';
        userInput.value = localStorage.getItem('username') || '';
        currencySelect.value = localStorage.getItem('currency') || 'TON';
        statusOutput.textContent = 'Ожидание оплаты...';
        checkPurchaseStatus(savedPurchaseId);
    }
}

// Обработка покупки
async function buyStars() {
    const amount = Number(quantityInput2.value);
    const username = userInput.value;
    const currency = currencySelect.value;
    if (!amount || !username || !currency) {
        showNotification('Заполните все поля', 'error');
        return;
    }
    try {
        const response = await fetch('/api/purchase', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount,
                recipient_username: username,
                currency,
                user_id: localStorage.getItem("telegram_user_id") || null
            })
        });
        const data = await response.json();
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            purchaseId = data.purchase_id;
            if (!window.Telegram || !window.Telegram.WebApp) {
                localStorage.setItem("purchase_id", data.purchase_id);
                localStorage.setItem("amount", amount);
                localStorage.setItem("username", username);
                localStorage.setItem("currency", currency);
            }
            statusOutput.textContent = 'Ожидание оплаты...';
            showNotification('Покупка создана, перенаправление на оплату...', 'success');
            if (data.invoice_url) {
                window.open(data.invoice_url, "_blank");
            } else {
                checkPurchaseStatus(purchaseId);
            }
        }
    } catch (e) {
        showNotification('Ошибка сервера', 'error');
    }
}

// Проверка статуса покупки
function checkPurchaseStatus(purchaseId) {
    const interval = setInterval(() => {
        fetch(`/api/purchase/${purchaseId}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    statusOutput.textContent = `Ошибка: ${data.error}`;
                    showNotification(`Ошибка: ${data.error}`, 'error');
                    clearInterval(interval);
                    if (!window.Telegram || !window.Telegram.WebApp) {
                        localStorage.clear();
                    }
                } else if (data.status === 'completed') {
                    statusOutput.textContent = 'Покупка завершена!';
                    showNotification('Покупка успешно завершена!', 'success');
                    clearInterval(interval);
                    if (!window.Telegram || !window.Telegram.WebApp) {
                        localStorage.clear();
                    }
                    quantityInput2.value = '';
                    userInput.value = userInput.value;
                    currencySelect.value = 'TON';
                    updatePrice();
                } else if (data.status === 'failed') {
                    statusOutput.textContent = `Ошибка: свяжитесь с поддержкой: https://t.me/HappySupportStars`;
                    showNotification(`Ошибка: свяжитесь с поддержкой: https://t.me/HappySupportStars`, 'error');
                    clearInterval(interval);
                    if (!window.Telegram || !window.Telegram.WebApp) {
                        localStorage.clear();
                    }
                } else if (data.status === 'cancelled') {
                    statusOutput.textContent = 'Оплата не произошла в течение 15 минут, счет отменен.';
                    showNotification('Оплата не произошла в течение 15 минут, счет отменен.', 'error');
                    clearInterval(interval);
                    if (!window.Telegram || !window.Telegram.WebApp) {
                        localStorage.clear();
                    }
                }
            })
            .catch(() => {
                statusOutput.textContent = 'Ошибка проверки статуса';
                showNotification('Ошибка проверки статуса', 'error');
                clearInterval(interval);
                if (!window.Telegram || !window.Telegram.WebApp) {
                    localStorage.clear();
                }
            });
    }, 5000);
}

// Обработчики событий
quantityInput2.addEventListener('input', () => {
    const quantity = parseInt(quantityInput2.value);
    if (quantity) {
        starsOptions.forEach(option => option.checked = false);
    }
    updatePrice();
});

starsOptions.forEach(option => {
    option.addEventListener('change', () => {
        quantityInput2.value = option.value;
        updatePrice();
    });
});

currencySelect.addEventListener('change', updatePrice);
buyBtn.addEventListener('click', buyStars);