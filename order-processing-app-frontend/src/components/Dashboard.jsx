// Dashboard.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Dashboard.css'; // Ensure this is imported
import { useAuth } from '../contexts/AuthContext';

// Added prop: initialView can be 'orders' or 'dailySales'
function Dashboard({ initialView = 'orders' }) {
    const { currentUser, loading: authLoading } = useAuth();
    const navigate = useNavigate();
    const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

    // The view to display, controlled by prop
    const [currentView, setCurrentView] = useState(initialView);

    // Orders Tab State
    const [orders, setOrders] = useState([]);
    const [loadingOrders, setLoadingOrders] = useState(initialView === 'orders');
    const [errorOrders, setErrorOrders] = useState(null);
    const [filterStatus, setFilterStatus] = useState('new');
    const [ingesting, setIngesting] = useState(false);
    const [ingestionMessage, setIngestionMessage] = useState('');
    const [statusCounts, setStatusCounts] = useState({});
    const [loadingCounts, setLoadingCounts] = useState(initialView === 'orders');
    const [hasPendingOrInternational, setHasPendingOrInternational] = useState(false);

    // Daily Sales Tab State
    const [dailyRevenueData, setDailyRevenueData] = useState([]);
    const [loadingRevenue, setLoadingRevenue] = useState(initialView === 'dailySales');
    const [errorRevenue, setErrorRevenue] = useState(null);

    // --- Helper Functions ---
    const formatShippingMethod = (method) => {
        if (!method) { return 'N/A'; }
        if (typeof method !== 'string') { return String(method); }
        if (method.trim().toLowerCase() === 'free shipping') { return 'UPS® Ground'; }
        const regex = /.*\((.*)\)/;
        const match = method.match(regex);
        if (match && match[1]) { return match[1].trim(); }
        return method.trim();
    };

    const formatCurrencyDisplay = (amount) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
    };

    // --- Data Fetching for Orders View ---
    const fetchOrders = useCallback(async (signal) => {
        if (!currentUser) {
            setOrders([]);
            setLoadingOrders(false);
            setErrorOrders(null);
            return;
        }
        setLoadingOrders(true);
        setErrorOrders(null);
        if (!VITE_API_BASE_URL) {
            setErrorOrders("API URL not configured.");
            setLoadingOrders(false);
            return;
        }
        try {
            const token = await currentUser.getIdToken(true);
            const statusParam = filterStatus ? `?status=${encodeURIComponent(filterStatus)}` : '';
            const displayOrdersApiUrl = `${VITE_API_BASE_URL}/orders${statusParam}`;
            const response = await fetch(displayOrdersApiUrl, {
                signal,
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (signal && signal.aborted) return;
            if (!response.ok) {
                let errorMsg = `Failed to load orders. Status: ${response.status}`;
                if (response.status === 401 || response.status === 403) {
                    errorMsg = "Unauthorized to fetch orders. Please log in again.";
                } else {
                    try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) { /* ignore */ }
                }
                throw new Error(errorMsg);
            }
            const data = await response.json();
            if (signal && signal.aborted) return;
            if (!Array.isArray(data)) throw new Error("Received orders data is not in the expected array format.");
            data.sort((a, b) => (new Date(b.order_date) || 0) - (new Date(a.order_date) || 0));
            setOrders(data || []);
        } catch (err) {
            if (err.name !== 'AbortError') {
                setErrorOrders(err.message || "Failed to fetch orders.");
                setOrders([]);
            }
        } finally {
            if (!signal || !signal.aborted) setLoadingOrders(false);
        }
    }, [filterStatus, VITE_API_BASE_URL, currentUser]);

    const fetchStatusCounts = useCallback(async (signal) => {
        if (!currentUser) {
            setStatusCounts({});
            setLoadingCounts(false);
            setHasPendingOrInternational(false);
            return;
        }
        setLoadingCounts(true);
        if (!VITE_API_BASE_URL) {
            setLoadingCounts(false);
            return;
        }
        try {
            const token = await currentUser.getIdToken(true);
            const countsApiUrl = `${VITE_API_BASE_URL}/orders/status-counts`;
            const response = await fetch(countsApiUrl, {
                signal,
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (signal && signal.aborted) return;
            if (!response.ok) {
                if(response.status === 401 || response.status === 403) {
                    console.error("Unauthorized to fetch status counts.");
                    setErrorOrders(prevError => prevError ? prevError + " Additionally, failed to load status counts (unauthorized)." : "Failed to load status counts (unauthorized).");
                }
                throw new Error('Failed to fetch status counts');
            }
            const counts = await response.json();
            if (signal && signal.aborted) return;
            setStatusCounts(counts || {});
            setHasPendingOrInternational(!!(counts && (counts.pending > 0 || counts.international_manual > 0)));
        } catch (error) {
            console.error("Error fetching status counts:", error.message);
            if (!errorOrders) setErrorOrders("Could not load status counts.");
            setStatusCounts({});
            setHasPendingOrInternational(false);
        } finally {
            if (!signal || !signal.aborted) setLoadingCounts(false);
        }
    }, [VITE_API_BASE_URL, currentUser, errorOrders]);

    const handleIngestOrders = useCallback(async () => {
        if (!VITE_API_BASE_URL) {
            setIngestionMessage("Error: API URL not configured.");
            return;
        }
        if (!currentUser) {
            setIngestionMessage("Please log in to ingest orders.");
            return;
        }
        setIngesting(true);
        setIngestionMessage('Importing orders from BigCommerce...');
        try {
            const token = await currentUser.getIdToken(true);
            const ingestApiUrl = `${VITE_API_BASE_URL}/ingest_orders`;
            const response = await fetch(ingestApiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({})
            });
            const result = await response.json().catch(() => ({
                message: `Ingestion request failed with status ${response.status}. Response not JSON.`
            }));
            if (!response.ok) {
                let errorMsg = `Error: ${result.message || result.error || `Failed with status ${response.status}`}`;
                 if (response.status === 401 || response.status === 403) {
                    errorMsg = "Unauthorized to ingest orders. Please log in again.";
                }
                setIngestionMessage(errorMsg);
            } else {
                setIngestionMessage(result.message || "Ingestion process completed successfully.");
                if (currentView === 'orders') {
                    const abortController = new AbortController();
                    fetchOrders(abortController.signal);
                    fetchStatusCounts(abortController.signal);
                }
            }
        } catch (err) {
            setIngestionMessage(`Ingestion request failed: ${err.message || 'Network error or invalid response'}`);
        } finally {
            setIngesting(false);
            setTimeout(() => setIngestionMessage(''), 7000);
        }
    }, [VITE_API_BASE_URL, currentUser, fetchOrders, fetchStatusCounts, currentView]);


    // --- Data Fetching for Daily Sales View ---
    const fetchDailyRevenue = useCallback(async (signal) => {
        if (!currentUser) {
            setDailyRevenueData([]);
            setLoadingRevenue(false);
            setErrorRevenue(null);
            return;
        }
        setLoadingRevenue(true);
        setErrorRevenue(null);
        if (!VITE_API_BASE_URL) {
            setErrorRevenue("API URL not configured.");
            setLoadingRevenue(false);
            return;
        }
        try {
            const token = await currentUser.getIdToken(true);
            const revenueApiUrl = `${VITE_API_BASE_URL}/reports/daily-revenue`;
            const response = await fetch(revenueApiUrl, {
                signal,
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (signal && signal.aborted) return;
            if (!response.ok) {
                let errorMsg = `Failed to load revenue. Status: ${response.status}`;
                 if (response.status === 401 || response.status === 403) {
                    errorMsg = "Unauthorized to fetch revenue. Please log in again.";
                } else {
                    try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) { /* ignore */ }
                }
                throw new Error(errorMsg);
            }
            const data = await response.json();
            if (signal && signal.aborted) return;
            if (!Array.isArray(data)) throw new Error("Received revenue data is not in the expected array format.");
            setDailyRevenueData(data || []);
        } catch (err) {
            if (err.name !== 'AbortError') {
                setErrorRevenue(err.message || "Failed to fetch daily revenue.");
                setDailyRevenueData([]);
            }
        } finally {
            if (!signal || !signal.aborted) setLoadingRevenue(false);
        }
    }, [VITE_API_BASE_URL, currentUser]);


    // --- Effects ---
    useEffect(() => {
        setCurrentView(initialView);
    }, [initialView]);

    useEffect(() => {
        if (authLoading) {
            if (currentView === 'orders') setLoadingOrders(true);
            if (currentView === 'dailySales') setLoadingRevenue(true);
            return;
        }
        if (!currentUser) {
            setOrders([]);
            setStatusCounts({});
            setLoadingOrders(false);
            setLoadingCounts(false);
            setErrorOrders(null);
            setHasPendingOrInternational(false);
            setDailyRevenueData([]);
            setLoadingRevenue(false);
            setErrorRevenue(null);
            return;
        }

        const abortController = new AbortController();
        if (currentView === 'orders') {
            fetchOrders(abortController.signal);
            fetchStatusCounts(abortController.signal);
        } else if (currentView === 'dailySales') {
            fetchDailyRevenue(abortController.signal);
        }
        return () => abortController.abort();
    }, [currentUser, authLoading, currentView, fetchOrders, fetchStatusCounts, fetchDailyRevenue, filterStatus]);


    // --- Event Handlers ---
    const handleRowClick = (orderId) => navigate(`/orders/${orderId}`);
    const handleLinkClick = (e) => e.stopPropagation();
    const handleFilterChange = (event) => setFilterStatus(event.target.value);

    // --- Render Logic ---
    const orderedDropdownStatuses = [
        { value: 'new', label: 'New' },
        { value: 'RFQ Sent', label: 'RFQ Sent' },
        { value: 'pending', label: 'Pending' },
        { value: 'international_manual', label: 'International' },
        { value: 'Processed', label: 'Processed' },
        { value: 'Completed Offline', label: 'Completed Offline' }
    ];

    // Get today's date in UTC, formatted as YYYY-MM-DD
    // 'en-CA' locale is a common way to get this format.
    const todayUTCString = new Date().toLocaleDateString('en-CA', { timeZone: 'UTC' });


    if (authLoading && !currentUser) {
        return <div className="loading-message">Loading session...</div>;
    }

    if (!currentUser) {
        return (
            <div className="dashboard-container" style={{ textAlign: 'center', marginTop: '50px' }}>
                <h2>G1 PO App Dashboard</h2>
                <p className="empty-list-message">Please <Link to="/login">log in</Link> to view the dashboard.</p>
            </div>
        );
    }

    return (
        <div className="dashboard-container">
            <h2 style={{ lineHeight: '1.2', marginBottom: '20px', textShadow: '1px 1px 2px rgba(0,0,0,0.2)' }}>
                <span style={{ fontSize: '90%', fontWeight: '600', display: 'block', color: 'var(--primary-accent-dark)' }}>
                    Global One Technology
                </span>
                <span style={{ fontSize: '70%', fontWeight: '900', display: 'block', color: 'var(--primary-accent-dark)', letterSpacing: '0.3em' }}>{currentView === 'dailySales' ? 'Daily Sales Report' : 'Dashboard'}</span>
            </h2>

            {currentView === 'orders' && (
                <>
                    <div className="dashboard-controls-bar">
                        <div className="dashboard-filters">
                            <label htmlFor="statusFilter" style={{ fontWeight: '500', color: 'var(--text-main)'}}>
                                Filter by Status:
                                {hasPendingOrInternational && <span style={{ color: 'red', marginLeft: '2px', fontWeight: 'bold' }}>*</span>}
                            </label>
                            <select
                                id="statusFilter"
                                value={filterStatus}
                                onChange={handleFilterChange}
                                style={{ padding: '8px 10px', borderRadius: '4px', border: '1px solid var(--border-input)', opacity: '65%'}}
                                disabled={loadingCounts || ingesting}
                            >
                                {orderedDropdownStatuses.map(statusObj => {
                                    const count = statusCounts[statusObj.value];
                                    const displayCount = (count !== undefined) ? ` (${count})` : ' (0)';
                                    const optionAsterisk = (
                                        (statusObj.value === 'pending' && statusCounts.pending > 0) ||
                                        (statusObj.value === 'international_manual' && statusCounts.international_manual > 0)
                                    ) ? '*' : '';
                                    return (
                                        <option key={statusObj.value} value={statusObj.value}>
                                            {statusObj.label}{displayCount}{optionAsterisk}
                                        </option>
                                    );
                                })}
                            </select>
                        </div>
                    </div>

                    {errorOrders && <div className="error-message" style={{ marginBottom: '15px' }}>Error: {errorOrders}</div>}
                    {loadingOrders && orders.length === 0 && !errorOrders && <div className="loading-message">Loading orders...</div>}
                    {loadingOrders && orders.length > 0 && <div className="loading-message" style={{marginTop: '10px', marginBottom: '10px'}}>Refreshing orders...</div>}


                    {orders.length === 0 && !loadingOrders && !errorOrders ? (
                        <p className="empty-list-message">No orders found{filterStatus ? ` with status '${orderedDropdownStatuses.find(s => s.value === filterStatus)?.label || filterStatus}'` : ''}.</p>
                    ) : !errorOrders && orders.length > 0 && (
                        <div className="table-responsive-container">
                            <table className="order-table">
                                <thead>
                                    <tr>
                                        <th>Order #</th><th>Order Date</th><th>Customer</th>
                                        <th className="hide-mobile">Status</th>
                                        <th>Payment Method</th>
                                        <th>Ship Method</th><th>Ship To</th>
                                        <th className="hide-mobile">Int'l</th><th className="hide-mobile">Created</th>
                                        <th>Comments</th><th>Total</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {orders.map(order => {
                                        const orderDate = order.order_date ? new Date(order.order_date) : null;
                                        const formattedDate = orderDate ? orderDate.toLocaleDateString() : 'N/A';
                                        const hasCustomerNotes = order.customer_notes && order.customer_notes.trim() !== '';
                                        const initialCommentLength = 70;
                                        const displayShippingMethod = formatShippingMethod(order.customer_shipping_method);
                                        return (
                                            <tr key={order.id} className="clickable-row" onClick={() => handleRowClick(order.id)}
                                                title={hasCustomerNotes ? `Comments: ${order.customer_notes.substring(0,100)}${order.customer_notes.length > 100 ? '...' : ''}` : 'View Order Details'}>
                                                <td data-label="Order #">
                                                    <Link to={`/orders/${order.id}`} onClick={handleLinkClick}>{order.bigcommerce_order_id || order.id}</Link>
                                                    <span className={`order-status-badge-table status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`} style={{display: 'block', marginTop: '5px', textAlign:'center'}}>{order.status || 'Unknown'}</span>
                                                </td>
                                                <td data-label="Order Date" className="mobile-order-date-cell">{formattedDate}</td>
                                                <td data-label="Customer">{order.customer_company || order.customer_name || 'N/A'}</td>
                                                <td data-label="Status" className="hide-mobile">
                                                    <span className={`order-status-badge-table status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>{order.status || 'Unknown'}</span>
                                                </td>
                                                <td data-label="Paid by">{order.payment_method || 'N/A'}</td>
                                                <td data-label="Ship Method">{displayShippingMethod}</td>
                                                <td data-label="Ship To">{`${order.customer_shipping_city || '?'}, ${order.customer_shipping_state || '?'}`}</td>
                                                <td data-label="Int'l" className="hide-mobile">{order.is_international ? 'Yes' : 'No'}</td>
                                                <td data-label="Created" className="hide-mobile">{order.created_at ? new Date(order.created_at).toLocaleDateString() : 'N/A'}</td>
                                                <td data-label="Comments" className={!hasCustomerNotes ? 'no-label' : ''}>
                                                    <span className="comment-value">{hasCustomerNotes ? (<>{order.customer_notes.substring(0, initialCommentLength)}{order.customer_notes.length > initialCommentLength ? '...' : ''}</>) : (null)}</span>
                                                </td>
                                                <td data-label="Total" className="total-column">${(order.total_sale_price && !isNaN(parseFloat(order.total_sale_price))) ? parseFloat(order.total_sale_price).toFixed(2) : '0.00'}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                     <div className="ingest-controls-sticky-wrapper">
                        <div className="ingest-controls">
                            {ingestionMessage &&
                                <div
                                    className="ingestion-message"
                                    style={{
                                        color: ingestionMessage.toLowerCase().includes('error') || ingestionMessage.toLowerCase().includes('failed') ? 'var(--error-text)' : 'var(--success-text)',
                                        alignSelf: 'center',
                                        fontWeight: 500,
                                        marginBottom: currentUser ? '8px' : '0'
                                    }}>
                                    {ingestionMessage}
                                </div>
                            }
                            {currentUser && (
                                <button
                                    onClick={handleIngestOrders}
                                    disabled={ingesting || loadingCounts || loadingOrders}
                                    className="btn btn-gradient btn-shadow-lift btn-primary"
                                >
                                    {ingesting ? 'Importing...' : (loadingCounts ? 'Loading Filters...' : 'IMPORT NEW ORDERS')}
                                </button>
                            )}
                        </div>
                    </div>
                </>
            )}

            {currentView === 'dailySales' && (
                <div className="revenue-tab-content card">
                    <h3>Daily Revenue - Last 14 Days</h3>
                    {loadingRevenue && <p className="loading-message">Loading revenue data...</p>}
                    {errorRevenue && <p className="error-message">Error loading revenue: {errorRevenue}</p>}
                    {!loadingRevenue && !errorRevenue && dailyRevenueData.length === 0 && <p className="empty-list-message">No revenue data available for the last 14 days.</p>}
                    {!loadingRevenue && !errorRevenue && dailyRevenueData.length > 0 && (
                        <div className="daily-revenue-list">
                            {dailyRevenueData.map(item => {
                                // MODIFIED: Conditional rendering for "today (UTC)" with zero sales
                                if (item.sale_date === todayUTCString && item.daily_revenue === 0) {
                                    return null; // Don't render this item
                                }
                                return (
                                    <div key={item.sale_date} className="daily-revenue-item">
                                        <span style={{ marginRight: 'auto' }}> {/* Date Span */}
                                            {new Date(item.sale_date + 'T00:00:00Z').toLocaleDateString('en-US', {
                                                year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC'
                                            })}
                                        </span>
                                        <span style={{ /* Revenue Span */
                                            fontWeight: item.daily_revenue > 0 ? 'bold' : 'normal',
                                            color: item.daily_revenue > 0 ? 'green' : (item.daily_revenue === 0 ? 'orange' : 'inherit'),
                                            textAlign: 'right'
                                        }}>
                                            {formatCurrencyDisplay(item.daily_revenue)}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default Dashboard;
