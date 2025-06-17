const portfolioChartContext = document.getElementById('portfolioChart').getContext('2d');
let portfolioChart;

const updateDashboard = async () => {
    try {
        const response = await fetch('/data');
        if (response.status === 401) { // Unauthorized, means not logged in
            window.location.href = '/login'; // Redirect to login page
            return;
        }
        const data = await response.json();

        // Update Status
        document.getElementById('status-message').textContent = data.status;

        // Update USDT Balance
        document.getElementById('usdt-balance').textContent = parseFloat(data.usdt).toFixed(2);

        // Update Next Cycle Time
        const nextCycleTimeElement = document.getElementById('next-cycle-time');
        if (data.next_cycle_time && data.next_cycle_time > 0) {
            const date = new Date(data.next_cycle_time * 1000); // Convert to milliseconds
            nextCycleTimeElement.textContent = date.toLocaleString(); // Format to local time string
        } else {
            nextCycleTimeElement.textContent = 'Aguardando...';
        }

        // Update Portfolio
        const portfolioList = document.getElementById('portfolio-list');
        portfolioList.innerHTML = ''; // Clear previous items
        let totalPortfolioValue = 0;

        // Emojis for crypto assets - extend as needed
        const cryptoEmojis = {
            'BTCUSDT': '₿', 'ETHUSDT': 'Ξ', 'SOLUSDT': ' Solana', 'BNBUSDT': ' BNB',
            'DOGEUSDT': '🐕', 'LINKUSDT': '🔗', 'ADAUSDT': ' Cardano', 'FETUSDT': '🤖',
            'AVAXUSDT': '❄️', 'OMUSDT': '☸️', 'RNDRUSDT': '💡', 'TRUMPUSDT': '🏛️'
        };

        for (const symbol_pair in data.portfolio) {
            const item = data.portfolio[symbol_pair];
            const asset = symbol_pair.replace('USDT', '');
            const currentPrice = item.current_price;
            const amount = item.amount;
            const emoji = cryptoEmojis[symbol_pair] || '💎'; // Default emoji

            let valueUsdt = amount * currentPrice;
            if (symbol_pair === "USDT") {
                valueUsdt = amount; // USDT value is its amount
                totalPortfolioValue += valueUsdt; // Add USDT cash to total portfolio
                // Don't create a separate card for USDT cash, it's shown in usdt-balance
                continue; 
            }
            totalPortfolioValue += valueUsdt;

            const portfolioItem = `
                <div class="bg-gray-700 rounded-lg p-4 shadow-md flex items-center justify-between">
                    <div>
                        <h3 class="text-xl font-semibold">${asset} ${emoji}</h3>
                        <p class="text-gray-400">Preço: $${currentPrice ? parseFloat(currentPrice).toFixed(4) : 'N/A'}</p>
                        <p class="text-gray-400">Quantidade: ${parseFloat(amount).toFixed(4)}</p>
                    </div>
                    <div class="text-right">
                        <p class="text-green-300 text-lg font-bold">Valor: $${valueUsdt.toFixed(2)}</p>
                    </div>
                </div>
            `;
            portfolioList.insertAdjacentHTML('beforeend', portfolioItem);
        }

        // Update Total Performance Chart
        updatePortfolioChart(totalPortfolioValue);


        // Update History
        const historyList = document.getElementById('history-list');
        historyList.innerHTML = ''; // Clear previous items
        if (data.history && data.history.length > 0) {
            data.history.forEach(trade => {
                const tradeTypeClass = trade.type === 'BUY' ? 'text-green-400' : 'text-red-400';
                const tradeEntry = `
                    <div class="bg-gray-700 rounded-lg p-3 shadow-md">
                        <p class="text-sm text-gray-400">${new Date(trade.timestamp).toLocaleString()}</p>
                        <p class="${tradeTypeClass} font-semibold">${trade.type}: ${parseFloat(trade.quantity).toFixed(4)} ${trade.symbol.replace('USDT', '')} @ $${parseFloat(trade.price).toFixed(4)}</p>
                    </div>
                `;
                historyList.insertAdjacentHTML('afterbegin', tradeEntry); // Add to top
            });
        } else {
            historyList.innerHTML = '<p class="text-gray-500 text-center">Nenhum histórico de operações ainda.</p>';
        }

    } catch (error) {
        console.error('Erro ao buscar dados do dashboard:', error);
        // Pode adicionar uma mensagem de erro na UI
    }
};

const updatePortfolioChart = (totalValue) => {
    const labels = ['Portfólio Total', 'Outros Ativos']; // Simplificado
    const data = [totalValue, 0]; // Apenas o valor total do portfólio no momento

    if (portfolioChart) {
        portfolioChart.data.labels = labels;
        portfolioChart.data.datasets[0].data = data;
        portfolioChart.update();
    } else {
        portfolioChart = new Chart(portfolioChartContext, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: ['#8B5CF6', '#4B5563'], // Purple and gray
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#e2e8f0' // Light gray for legend text
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed !== null) {
                                    label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed);
                                }
                                return label;
                            }
                        }
                    }
                }
            }
        });
    }
};


// --- Animações e Botões ---
const welcomeSection = document.getElementById('welcome-section');
const welcomeText = document.getElementById('welcome-text');
const dashboardContent = document.getElementById('dashboard-content');
const sections = document.querySelectorAll('.section-reveal'); // Seleciona todas as seções que você quer revelar

const revealSections = () => {
    const windowHeight = window.innerHeight;
    const scrollY = window.scrollY;
    const welcomeHeight = welcomeSection.offsetHeight; // Get the height of the welcome section

    // Welcome section fade and slide effect
    if (scrollY < welcomeHeight) {
        const opacity = Math.max(0, 1 - scrollY / (welcomeHeight * 0.7)); // Fades out faster
        welcomeSection.style.opacity = opacity;
        
        // Slide up welcome text as it fades
        const translateY = Math.min(0, -scrollY * 0.2); // Slower slide
        welcomeText.style.transform = `translateY(${translateY}px)`;

        // Show dashboard content after welcome section is mostly out of view
        if (scrollY > welcomeHeight * 0.2) { // Adjust threshold as needed
            dashboardContent.style.opacity = 1;
            dashboardContent.style.transform = 'translateY(0)';
        } else {
            dashboardContent.style.opacity = 0;
            dashboardContent.style.transform = 'translateY(10px)'; // Start slightly lower
        }
    } else {
        welcomeSection.style.opacity = 0;
        dashboardContent.style.opacity = 1;
        dashboardContent.style.transform = 'translateY(0)';
    }


    sections.forEach(section => {
        const sectionTop = section.getBoundingClientRect().top;
        if (sectionTop < windowHeight - 100) { // When section is 100px from bottom of viewport
            section.classList.add('revealed');
        } else {
            section.classList.remove('revealed'); // Remove if scrolled back up
        }
    });
};

// Initial calls and event listeners
document.addEventListener('DOMContentLoaded', () => {
    updateDashboard(); // Initial data load
    setInterval(updateDashboard, 5000); // Update dashboard every 5 seconds

    revealSections(); // Initial reveal check
    window.addEventListener('scroll', revealSections); // Reveal sections on scroll

    // Botão de Iniciar Bot
    document.getElementById('start-bot-btn').addEventListener('click', async () => {
        const statusMessage = document.getElementById('status-message');
        statusMessage.textContent = 'Iniciando bot... Por favor, aguarde.';
        try {
            const response = await fetch('/start_bot', { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                statusMessage.textContent = data.message;
            } else {
                statusMessage.textContent = `Erro ao iniciar bot: ${data.message}`;
                alert(`Erro: ${data.message}`);
            }
        } catch (error) {
            console.error('Erro ao comunicar com o servidor:', error);
            statusMessage.textContent = 'Erro de comunicação com o servidor.';
            alert('Erro de comunicação com o servidor ao iniciar o bot.');
        }
    });

    // Botão de Parar Bot
    document.getElementById('stop-bot-btn').addEventListener('click', async () => {
        const statusMessage = document.getElementById('status-message');
        statusMessage.textContent = 'Parando bot...';
        try {
            const response = await fetch('/stop_bot', { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                statusMessage.textContent = data.message;
            } else {
                statusMessage.textContent = `Erro ao parar bot: ${data.message}`;
                alert(`Erro: ${data.message}`);
            }
        } catch (error) {
            console.error('Erro ao comunicar com o servidor:', error);
            statusMessage.textContent = 'Erro de comunicação com o servidor.';
            alert('Erro de comunicação com o servidor ao parar o bot.');
        }
    });
});