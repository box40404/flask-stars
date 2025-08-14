// Обновление текста кнопки при выборе количества звезд
    const starOptions = document.querySelectorAll('input[name="stars"]');
    const buyButton = document.getElementById('buyButton');
    const quantityInput = document.getElementById('quantityInput');
    const usernameInput = document.getElementById('usernameInput');
    
    // Обновление текста кнопки при выборе радио-кнопок
    starOptions.forEach(option => {
        option.addEventListener('change', function() {
            if (this.checked) {
                const starCount = this.value;
                buyButton.textContent = `Купить ${starCount} звёзд`;
                quantityInput.value = starCount; // Sync input with radio selection
            }
        });
    });
    
    // Обновление текста кнопки при вводе в поле количества
    quantityInput.addEventListener('input', function() {
        const value = parseInt(this.value);
        if (value >= 50 && value <= 10000) {
            buyButton.textContent = `Купить ${value} звёзд`;
            // Uncheck all radio buttons if custom input is used
            starOptions.forEach(option => {
                option.checked = false;
            });
        }
    });
    
    // Валидация количества звезд
    quantityInput.addEventListener('input', function() {
        const value = parseInt(this.value);
        if (value < 50 || value > 10000) {
            this.style.borderColor = '#ff6b6b';
        } else {
            this.style.borderColor = '';
        }
    });
    
    // Обработка кнопки покупки
    buyButton.addEventListener('click', function() {
        const username = usernameInput.value.trim();
        const quantity = quantityInput.value.trim();
        
        if (!username) {
            alert('Введите имя пользователя Telegram');
            usernameInput.focus();
            return;
        }
        
        if (!quantity || quantity < 50 || quantity > 10000) {
            alert('Введите корректное количество звезд (от 50 до 10,000)');
            quantityInput.focus();
            return;
        };
    });
    