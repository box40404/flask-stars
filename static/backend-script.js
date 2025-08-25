const userInput = document.getElementById('usernameInput');
const quantityInput2 = document.getElementById('starInput');
const currencySelect = document.getElementById('currencySelect');
const costOutput = document.getElementById('costOutput');
const currencyOutput = document.getElementById('currencyOutput');
const statusDisplay = document.querySelector('.status-display');
const statusOutput = document.getElementById('statusOutput');
const buyBtn = document.querySelector('.buy-btn');
const buyButtonStars = document.getElementById('buyButtonStars');
const starsOptions = document.querySelectorAll('.star-btn');
const telegramAuthButton = document.getElementById('telegramAuthButton');
const userProfile = document.getElementById('userProfile');
const userAvatar = document.getElementById('userAvatar');
const userName = document.getElementById('userName');
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
let currentUserId = null;

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
    fetch('/api/prices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            initData: window.Telegram?.WebApp?.initData || null,
            user_id: window.Telegram?.WebApp?.initData ? currentUserId : getCookie("user_id") || null,
            amount: amount
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification(`Ошибка загрузки цен`, 'error');
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

function getCookie(name) {
    const cookies = document.cookie.split(';').map(cookie => cookie.trim());
    for (const cookie of cookies) {
        if (cookie.startsWith(`${name}=`)) {
            const value = decodeURIComponent(cookie.substring(name.length + 1));
            return value;
        }
    }
    return null;
}

if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
}

const initData = window.Telegram?.WebApp?.initData || "";
if (initData) {
    fetch('/api/verify-init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData })
    })
        .then(response => response.json())
        .then(data => {
            if (data.user_id) {
                currentUserId = data.user_id;
                userInput.value = `@${data.username}`;
                if (userProfile && userName) {
                    userProfile.style.display = 'flex';
                    userName.textContent = data.fullname;
                    telegramAuthButton.style.display = 'none';
                }
                updatePrice();
            } else {
                showNotification(`Ошибка авторизации`, 'error');
                updatePrice();
            }
        })
        .catch(() => {
            showNotification('Ошибка сервера при проверке авторизации', 'error');
            updatePrice();
        });
} else {
    // Проверяем токен из URL
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (token) {
        fetch('/api/verify-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        })
            .then(response => response.json())
            .then(data => {
                if (data.user_id) {
                    userInput.value = `@${data.username}`;
                    if (userProfile && userName) {
                        userProfile.style.display = 'flex';
                        userName.textContent = data.fullname || data.username;
                        telegramAuthButton.style.display = 'none';
                    }
                    updatePrice();
                    // Очищаем URL
                    window.history.replaceState({}, document.title, window.location.pathname);
                } else {
                    showNotification(`Ошибка авторизации`, 'error');
                    updatePrice();
                }
            })
            .catch(() => {
                showNotification('Ошибка сервера при проверке токена', 'error');
                updatePrice();
            });
    } else {
        const savedUserId = getCookie('user_id');
        if (savedUserId) {
            const savedUsername = getCookie('username');
            const savedFullName = getCookie('fullname');
            userInput.value = `@${savedUsername}`;
            userProfile.style.display = 'flex';
            userName.textContent = savedFullName;
            telegramAuthButton.style.display = 'none';
            updatePrice();
        } else {
            updatePrice();
        }
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
                user_id: window.Telegram?.WebApp?.initData ? currentUserId : getCookie("user_id") || null
            })
        });
        const data = await response.json();
        if (data.error) {
            showNotification('Ошибка при создании покупки', 'error');
        } else {
            purchaseId = data.purchase_id;
            statusOutput.textContent = 'Ожидание оплаты...';
            showNotification('Покупка создана, перенаправление на оплату...', 'success');
            if (data.qr_code) {
                document.getElementById('payment-message').textContent = data.payment_message;
                document.getElementById('payment-qr').src = data.qr_code;
                document.getElementById('payment-block').style.display = 'block';
            } else if (data.invoice_url) {
                window.open(data.invoice_url, "_blank");
            }

            checkPurchaseStatus(data.purchase_id);
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
                    statusOutput.textContent = `Ошибка`;
                    showNotification(`Ошибка`, 'error');
                    clearInterval(interval);
                    document.getElementById('payment-block').style.display = 'none';
                    document.getElementById('payment-message').textContent = '';
                    document.getElementById('payment-qr').src = '';
                } else if (data.status === 'completed') {
                    statusOutput.textContent = 'Покупка завершена!';
                    showNotification('Покупка успешно завершена!', 'success');
                    clearInterval(interval);
                    document.getElementById('payment-block').style.display = 'none';
                    document.getElementById('payment-message').textContent = '';
                    document.getElementById('payment-qr').src = '';
                    quantityInput2.value = '';
                    userInput.value = userInput.value;
                    currencySelect.value = 'TON';
                    updatePrice();
                } else if (data.status === 'failed') {
                    statusOutput.textContent = `Ошибка: свяжитесь с поддержкой: https://t.me/HappySupportStars`;
                    showNotification(`Ошибка: свяжитесь с поддержкой: https://t.me/HappySupportStars`, 'error');
                    clearInterval(interval);
                    document.getElementById('payment-block').style.display = 'none';
                    document.getElementById('payment-message').textContent = '';
                    document.getElementById('payment-qr').src = '';
                } else if (data.status === 'cancelled') {
                    statusOutput.textContent = 'Оплата не произошла в течение 15 минут, счет отменен.';
                    showNotification('Оплата не произошла в течение 15 минут, счет отменен.', 'error');
                    clearInterval(interval);
                    document.getElementById('payment-block').style.display = 'none';
                    document.getElementById('payment-message').textContent = '';
                    document.getElementById('payment-qr').src = '';
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

(async function () {
    try {
        const response = await fetch('/api/statistics', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (data.error) {
            console.error('Statistics error:', data.error);
            showNotification('Ошибка загрузки статистики', 'error');
            return;
        }
        document.querySelector('.stat-1 .stat-number').textContent = data.total_stars_sent.toLocaleString();
        document.querySelector('.stat-2 .stat-number').textContent = data.yesterday_stars_sent.toLocaleString();
        document.querySelector('.stat-3 .stat-number').textContent = data.today_stars_sent.toLocaleString();
    } catch (e) {
        console.error('Error fetching statistics:', e);
        showNotification('Ошибка загрузки статистики', 'error');
    }
})()

// Обработчик авторизации
telegramAuthButton.addEventListener('click', () => {
    const botUrl = `https://t.me/HappyStarsRobot?start=webapp-`;
    window.location.href = botUrl;
});

// Обработчики событий
quantityInput2.addEventListener('input', () => {
    const quantity = parseInt(quantityInput2.value);
    if (quantity) {
        starsOptions.forEach(option => option.checked = false);
    }
    updatePrice();
});

starsOptions.forEach(option => {
    option.addEventListener('click', () => {
        quantityInput2.value = option.dataset.amount;
        updatePrice();
    });
});

currencySelect.addEventListener('change', updatePrice);
buyBtn.addEventListener('click', buyStars);