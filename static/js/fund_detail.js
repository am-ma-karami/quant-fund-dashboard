async function fetchJSON(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `${url} failed: ${response.status}`
        );
    }

    return response.json();
}


async function loadFundChart(regNo) {
    const canvas = document.getElementById('fundChart');
    const ctx = canvas.getContext('2d');
    const loadingEl = document.getElementById('chart-loading');
    const errorEl = document.getElementById('chart-error');

    try {
        loadingEl.style.display = 'block';
        errorEl.style.display = 'none';
        canvas.style.display = 'none';

        const data = await fetchJSON(`/api/fund/${regNo}/chart`);

        if (!data.history || !data.history.length) {
            loadingEl.style.display = 'none';
            errorEl.textContent = 'داده‌ای برای نمایش چارت وجود ندارد.';
            errorEl.style.display = 'block';
            return;
        }

        // تبدیل داده‌ها برای Chart.js
        const labels = data.history.map(h => {
            const date = new Date(h.timestamp);
            return date.toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' });
        }).reverse();
        
        const navData = data.history.map(h => h.nav_stat).reverse();

        loadingEl.style.display = 'none';
        canvas.style.display = 'block';

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'NAV (ارزش واحد)',
                    data: navData,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    fill: true,
                    tension: 0.1,
                    pointRadius: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: 'NAV (ریال)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'تاریخ'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `NAV: ${context.raw.toLocaleString()} ریال`;
                            }
                        }
                    }
                }
            }
        });

        // Update last updated time
        if (data.fund && data.fund.last_updated) {
            const lastUpdated = new Date(data.fund.last_updated);
            document.getElementById('last_updated').textContent = lastUpdated.toLocaleTimeString('fa-IR');
        }
        
        if (data.fund && data.fund.nav_stat) {
            document.getElementById('nav_stat').textContent = data.fund.nav_stat.toLocaleString();
        }

    } catch (error) {
        console.error("Fund chart loading failed:", error);
        loadingEl.style.display = 'none';
        errorEl.textContent = 'دریافت اطلاعات چارت ناموفق بود.';
        errorEl.style.display = 'block';
    }
}


document.addEventListener(
    "DOMContentLoaded",
    () => {
        const fundDataEl = document.getElementById('fund-data');
        const regNo = fundDataEl ? fundDataEl.dataset.regNo : null;
        if (regNo) {
            loadFundChart(regNo);
        }
    }
);