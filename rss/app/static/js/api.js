(() => {
    if (!window.axios) {
        console.warn('Axios not loaded; auth interceptors disabled');
        return;
    }

    axios.interceptors.request.use(
        (config) => {
            const token = localStorage.getItem('auth_token');
            if (token) {
                config.headers = config.headers || {};
                config.headers.Authorization = `Bearer ${token}`;
            }
            return config;
        },
        (error) => Promise.reject(error)
    );

    axios.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error && error.response && error.response.status === 401) {
                localStorage.removeItem('auth_token');
                window.location.href = '/login';
            }
            return Promise.reject(error);
        }
    );
})();
