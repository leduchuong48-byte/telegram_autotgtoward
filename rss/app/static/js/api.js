(() => {
    if (!window.axios) {
        console.warn('Axios not loaded; auth interceptors disabled');
        return;
    }

    axios.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error && error.response && error.response.status === 401) {
                window.location.href = '/login';
            }
            return Promise.reject(error);
        }
    );
})();
