// Dashboard.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Dashboard.css';
import { useAuth } from '../contexts/AuthContext'; // Make sure path is correct

function Dashboard() {
    const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and authLoading state
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true); // For main order list
    const [error, setError] = useState(null);
    const navigate = useNavigate();
    const [filterStatus, setFilterStatus] = useState('new');
    const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

    const [ingesting, setIngesting] = useState(false);
    const [ingestionMessage, setIngestionMessage] = useState('');
    const [statusCounts, setStatusCounts] = useState({});
    const [loadingCounts, setLoadingCounts] = useState(true); // For status counts loading
    const [hasPendingOrInternational, setHasPendingOrInternational] = useState(false);

    const formatShippingMethod = (method) => {
        if (!method) { return 'N/A'; }
        if (typeof method !== 'string') { return String(method); }
        if (method.trim().toLowerCase() === 'free shipping') { return 'UPS® Ground'; }
        const regex = /.*\((.*)\)/;
        const match = method.match(regex);
        if (match && match[1]) { return match[1].trim(); }
        return method.trim();
    };

    const fetchOrders = useCallback(async (signal) => {
        if (!currentUser) {
            setOrders([]);
            setLoading(false);
            setError(null);
            return;
        }
        setLoading(true);
        setError(null);
        if (!VITE_API_BASE_URL) {
            setError("API URL not configured.");
            setLoading(false);
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
                    errorMsg = "Unauthorized to fetch orders. Your session might have expired. Please log in again.";
                    // Consider navigating to login: navigate('/login');
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
                setError(err.message || "Failed to fetch orders.");
                setOrders([]);
            }
        } finally {
            if (!signal || !signal.aborted) setLoading(false);
        }
    }, [filterStatus, VITE_API_BASE_URL, currentUser, navigate]); // Added navigate for potential redirect

    const fetchStatusCounts = useCallback(async (signal) => {
        if (!currentUser) {
            setStatusCounts({});
            setLoadingCounts(false);
            setHasPendingOrInternational(false);
            return;
        }
        if (!VITE_API_BASE_URL) {
            setLoadingCounts(false);
            return;
        }
        setLoadingCounts(true);
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
                    setError(prevError => prevError ? prevError + " Additionally, failed to load status counts (unauthorized)." : "Failed to load status counts (unauthorized).");
                }
                throw new Error('Failed to fetch status counts');
            }
            const counts = await response.json();
            if (signal && signal.aborted) return;
            setStatusCounts(counts || {});
            if (counts && ((counts.pending > 0) || (counts.international_manual > 0))) {
                setHasPendingOrInternational(true);
            } else {
                setHasPendingOrInternational(false);
            }
        } catch (error) {
            console.error("Error fetching status counts:", error.message);
            // Don't overwrite main error if it's already set from fetchOrders
            if (!error) setError("Could not load status counts.");
            setStatusCounts({});
            setHasPendingOrInternational(false);
        } finally {
            if (!signal || !signal.aborted) setLoadingCounts(false);
        }
    }, [VITE_API_BASE_URL, currentUser, error, navigate]); // Added error and navigate

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
                    // navigate('/login'); // Optionally redirect
                }
                setIngestionMessage(errorMsg);
            } else {
                setIngestionMessage(result.message || "Ingestion process completed successfully.");
                const abortController = new AbortController();
                fetchOrders(abortController.signal); // Use a new signal for these fetches
                fetchStatusCounts(abortController.signal);
            }
        } catch (err) {
            setIngestionMessage(`Ingestion request failed: ${err.message || 'Network error or invalid response'}`);
        } finally {
            setIngesting(false);
            setTimeout(() => setIngestionMessage(''), 7000);
        }
    }, [VITE_API_BASE_URL, currentUser, fetchOrders, fetchStatusCounts, navigate]); // Added navigate

    useEffect(() => {
        if (authLoading) { // If Firebase auth is still determining user state
            setLoading(true); // Keep main dashboard loading
            return;
        }
        if (currentUser) {
            const abortController = new AbortController();
            fetchOrders(abortController.signal);
            fetchStatusCounts(abortController.signal);
            return () => abortController.abort();
        } else {
            setOrders([]);
            setStatusCounts({});
            setLoading(false);
            setLoadingCounts(false);
            setError(null); // Clear errors when logged out
            setHasPendingOrInternational(false);
        }
    }, [currentUser, authLoading, fetchOrders, fetchStatusCounts]);

    const handleRowClick = (orderId) => navigate(`/orders/${orderId}`);
    const handleLinkClick = (e) => e.stopPropagation();
    const handleFilterChange = (event) => setFilterStatus(event.target.value);

    const orderedDropdownStatuses = [
        { value: 'new', label: 'New' },
        { value: 'RFQ Sent', label: 'RFQ Sent' },
        { value: 'pending', label: 'Pending' },
        { value: 'international_manual', label: 'International' },
        { value: 'Processed', label: 'Processed' },
        { value: 'Completed Offline', label: 'Completed Offline' }
    ];

    if (authLoading) {
        return <div className="loading-message">Loading session...</div>;
    }

    if (!currentUser) { // If not loading auth, and no user, show login prompt
        return (
            <div className="dashboard-container" style={{ textAlign: 'center', marginTop: '50px' }}>
                <h2>G1 PO App Dashboard</h2>
                <p className="empty-list-message">Please <Link to="/login">log in</Link> to view orders.</p>
            </div>
        );
    }

    // If user is present, but data is still loading for the first time
    if (loading && orders.length === 0 && !error){
        return <div className="loading-message">Loading orders...</div>;
    }

    return (
        <div className="dashboard-container">
            <h2 style={{ lineHeight: '1.2', marginBottom: '0.5em', textShadow: '1px 1px 2px rgba(0,0,0,0.2)' }}>
                <span style={{ fontSize: '90%', fontWeight: '600', display: 'block', color: 'var(--primary-accent-dark)' }}>
                    Global One Technology
                </span>
                <span style={{ fontSize: '70%', fontWeight: '900', display: 'block', color: 'var(--primary-accent-dark)', letterSpacing: '0.3em' }}>
                    Order Dashboard
                </span>
            </h2>

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
                        style={{ padding: '8px 10px', borderRadius: '4px', border: '1px solid var(--border-input)' }}
                        disabled={loadingCounts || ingesting} // Disable during count loading or ingestion
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

            {error && <div className="error-message" style={{ marginBottom: '15px' }}>Error: {error}</div>}
            {/* Show refreshing message only if orders are already present and we are re-fetching */}
            {loading && orders.length > 0 && <div className="loading-message" style={{marginTop: '10px', marginBottom: '10px'}}>Refreshing orders...</div>}

            {orders.length === 0 && !loading && !error ? (
                <p className="empty-list-message">No orders found{filterStatus ? ` for status '${orderedDropdownStatuses.find(s => s.value === filterStatus)?.label || filterStatus}'` : ''}.</p>
            ) : !error && orders.length > 0 && ( // Ensure orders exist before rendering table
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
                                marginRight: '15px', // Kept for spacing if needed
                                alignSelf: 'center',
                                fontWeight: 500,
                                marginBottom: currentUser ? '8px' : '0' // Add margin only if button is also shown
                            }}>
                            {ingestionMessage}
                        </div>
                    }
                    {currentUser && ( // Only show ingest button if user is logged in
                        // MODIFIED: Apply new global button classes
                        <button 
                            onClick={handleIngestOrders} 
                            disabled={ingesting || loadingCounts} 
                            className="btn btn-gradient btn-shadow-lift btn-primary" // Using primary color scheme
                        >
                            {ingesting ? 'Importing...' : (loadingCounts ? 'Loading Filters...' : 'IMPORT NEW ORDERS')}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Dashboard;
// --- END OF FILE Dashboard.jsx ---
