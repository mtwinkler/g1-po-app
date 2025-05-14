// --- START OF FILE Dashboard.jsx ---

import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Dashboard.css'; // Make sure this is imported

function Dashboard() {
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true); // For loading the main order list
    const [error, setError] = useState(null);     // For errors fetching the main order list
    const navigate = useNavigate();
    const [filterStatus, setFilterStatus] = useState('new');
    const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
    
    // State for Ingestion Button
    const [ingesting, setIngesting] = useState(false);
    const [ingestionMessage, setIngestionMessage] = useState('');

    const formatShippingMethod = (method) => {
        if (!method) { return 'N/A'; }
        if (typeof method !== 'string') { return String(method); }
        if (method.trim().toLowerCase() === 'free shipping') { return 'UPS® Ground'; }
        const regex = /.*\((.*)\)/;
        const match = method.match(regex);
        if (match && match[1]) { return match[1].trim(); }
        return method.trim();
    };

    // Function to call /ingest_orders, triggered by button
    const handleIngestOrders = useCallback(async () => {
        if (!VITE_API_BASE_URL) {
            console.error("Dashboard.jsx: VITE_API_BASE_URL is not defined for ingestion.");
            setIngestionMessage("Error: API URL not configured.");
            return;
        }
        console.log("Dashboard.jsx: 'Ingest New Orders' button clicked.");
        setIngesting(true);
        setIngestionMessage('Importing orders from BigCommerce...');
        // setError(null); // Don't clear main dashboard error for this separate action

        try {
            const ingestApiUrl = `${VITE_API_BASE_URL}/ingest_orders`;
            const response = await fetch(ingestApiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });

            const result = await response.json().catch(() => ({ // Try to parse JSON, provide fallback
                message: `Ingestion request failed with status ${response.status}. Response not JSON.`
            }));

            if (!response.ok) {
                console.error(`Dashboard.jsx: /ingest_orders call failed. Status: ${response.status}`, result);
                setIngestionMessage(`Error: ${result.message || result.error || `Failed with status ${response.status}`}`);
            } else {
                console.log("Dashboard.jsx: /ingest_orders call successful:", result.message);
                setIngestionMessage(result.message || "Ingestion process completed successfully.");
                // After successful ingestion, refresh the orders list
                fetchOrders(); // Assuming fetchOrders is stable via useCallback
            }
        } catch (err) {
            console.error("Dashboard.jsx: Exception calling /ingest_orders:", err);
            setIngestionMessage(`Ingestion request failed: ${err.message || 'Network error or invalid response'}`);
        } finally {
            setIngesting(false);
            // Optionally clear ingestion message after a few seconds
            setTimeout(() => setIngestionMessage(''), 7000); // Increased timeout
        }
    }, [VITE_API_BASE_URL]); // fetchOrders will be added if it's used directly here

    // fetchOrders now only fetches orders for display
    const fetchOrders = useCallback(async (signal) => {
        setLoading(true);
        // setError(null); // Clear previous display error before new fetch
        console.log("Dashboard.jsx: fetchOrders called. FilterStatus:", filterStatus);

        if (!VITE_API_BASE_URL) {
            console.error("Dashboard.jsx: VITE_API_BASE_URL is not defined. Cannot fetch orders.");
            setError("API URL not configured.");
            setLoading(false);
            return;
        }
        
        try {
            const statusParam = filterStatus ? `?status=${encodeURIComponent(filterStatus)}` : '';
            const displayOrdersApiUrl = `${VITE_API_BASE_URL}/orders${statusParam}`;
            console.log("Dashboard.jsx: Fetching display orders from:", displayOrdersApiUrl);

            const response = await fetch(displayOrdersApiUrl, { signal });
            console.log("Dashboard.jsx: Display orders fetch returned. Status:", response.status, "Ok:", response.ok);

            if (signal && signal.aborted) {
                console.log("Dashboard.jsx: Display orders fetch aborted (signal).");
                return; 
            }

            if (!response.ok) {
                let errorMsg = `Failed to load orders. Status: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.message || errorData.error || errorMsg;
                } catch(e) { /* Ignore if response not json, use status code error */ }
                throw new Error(errorMsg);
            }
            const data = await response.json();
            console.log("Dashboard.jsx: Display orders data parsed:", data);
            
            if (signal && signal.aborted) { // Check again after await response.json()
                console.log("Dashboard.jsx: Display orders fetch aborted before setting state.");
                return;
            }
            
            if (!Array.isArray(data)) {
                console.error("Dashboard.jsx: Orders data received is not an array!", data);
                throw new Error("Received orders data is not in the expected array format.");
            }

            data.sort((a, b) => {
                const dateA = a.order_date ? new Date(a.order_date) : 0;
                const dateB = b.order_date ? new Date(b.order_date) : 0;
                if (isNaN(dateA.getTime()) || isNaN(dateB.getTime())) return 0;
                return dateB - dateA;
            });
            setOrders(data || []);
            setError(null); // Clear any previous display error on success
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log('Dashboard.jsx: Display orders fetch aborted by AbortController.');
            } else {
                console.error("Error fetching display orders:", err);
                setError(err.message || "Failed to fetch orders.");
                setOrders([]); // Clear orders on error
            }
        } finally {
            if (!signal || !signal.aborted) { // Only set loading false if not aborted
                 setLoading(false);
                 console.log("Dashboard.jsx: Display orders loading set to false.");
            } else {
                console.log("Dashboard.jsx: Display orders finally block, fetch was aborted by signal.");
            }
        }
    }, [filterStatus, VITE_API_BASE_URL]);

    // useEffect for initial data load and when filterStatus changes
    useEffect(() => {
        console.log("Dashboard.jsx: useEffect for fetchOrders triggered. Filter status:", filterStatus);
        const abortController = new AbortController();
        fetchOrders(abortController.signal);

        return () => {
            console.log("Dashboard.jsx: useEffect cleanup for fetchOrders. Aborting. Filter status was:", filterStatus);
            abortController.abort();
        };
    }, [fetchOrders, filterStatus]); // fetchOrders depends on filterStatus & VITE_API_BASE_URL

    // Add fetchOrders to handleIngestOrders's dependency array if you call fetchOrders from there.
    // This is to satisfy eslint exhaustive-deps if it complains. fetchOrders is memoized.
    useEffect(() => {
        // This effect is just to make handleIngestOrders aware of the latest fetchOrders function
        // if fetchOrders were not stable (but it is due to useCallback).
        // Generally, if handleIngestOrders calls fetchOrders, fetchOrders should be a dependency of
        // the useCallback for handleIngestOrders.
    }, [fetchOrders]);


    const handleRowClick = (orderId) => {
        navigate(`/orders/${orderId}`);
    };

    const handleLinkClick = (e) => {
        e.stopPropagation();
    };

    const handleFilterChange = (event) => {
        setFilterStatus(event.target.value);
    };

    // Main loading state for the order list (only show "Loading orders..." on initial load)
    if (loading && orders.length === 0 && !error) return <div className="loading-message">Loading orders...</div>;

    return (
        <div className="dashboard-container">
            <h2 style={{ lineHeight: '1.2', marginBottom: '0.25em', textShadow: '1px 1px 2px rgba(0,0,0,0.2)' }}>
                <span style={{ fontSize: '90%', fontWeight: '600', display: 'block', color: 'var(--primary-accent-dark)' }}>
                    Global One Technology
                </span>
                <span style={{ fontSize: '70%', fontWeight: '900', display: 'block', color: 'var(--primary-accent-dark)', letterSpacing: '0.3em' }}>
                    Order Dashboard
                </span>
            </h2>

            <div className="dashboard-controls-bar">
                <div className="dashboard-filters">
                    <label htmlFor="statusFilter" style={{ fontWeight: '500', color: 'var(--text-main)'}}>Filter by Status:</label>
                    <select id="statusFilter" value={filterStatus} onChange={handleFilterChange} style={{ padding: '8px 10px', borderRadius: '4px', border: '1px solid var(--border-input)' }}>
                        <option value="new">New</option>
                        <option value="RFQ Sent">RFQ Sent</option>
                        <option value="Processed">Processed</option>
                        <option value="international_manual">International</option>
                        <option value="pending">Pending</option>
                        <option value="">All</option>
                    </select>
                </div>
            </div>

            {error && <div className="error-message" style={{ marginBottom: '15px' }}>Error loading orders: {error}</div>}
            
            {/* Show "Refreshing..." if loading is true AFTER initial load */}
            {loading && orders.length > 0 && <div className="loading-message" style={{marginTop: '10px', marginBottom: '10px'}}>Refreshing orders...</div>}

            {orders.length === 0 && !loading && !error ? (
                 <p className="empty-list-message">No orders found{filterStatus ? ` with status '${filterStatus}'` : ''}.</p>
            ) : !error && (
                <div className="table-responsive-container">
                    <table className="order-table">
                        {/* Table Head */}
                        <thead>
                            <tr>
                                <th>Order #</th><th>Order Date</th><th>Customer</th>
                                {/* This Status column is shown on desktop (hidden on mobile by .hide-mobile) */}
                                <th className="hide-mobile">Status</th> 
                                <th>Payment Method</th>
                                <th>Ship Method</th><th>Ship To</th>
                                <th className="hide-mobile">Int'l</th><th className="hide-mobile">Created</th>
                                <th>Comments</th><th>Total</th>
                            </tr>
                        </thead>
                        {/* Table Body */}
                        <tbody>
                            {orders.map(order => {
                                const orderDate = order.order_date ? new Date(order.order_date) : null;
                                const formattedDate = orderDate ? orderDate.toLocaleDateString() : 'N/A';
                                const formattedTime = orderDate ? orderDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }) : '';
                                const hasCustomerNotes = order.customer_notes && order.customer_notes.trim() !== '';
                                const initialCommentLength = 70;
                                const displayShippingMethod = formatShippingMethod(order.customer_shipping_method);
                                return (
                                    <tr key={order.id} className="clickable-row" onClick={() => handleRowClick(order.id)}
                                        title={hasCustomerNotes ? `Comments: ${order.customer_notes.substring(0,100)}${order.customer_notes.length > 100 ? '...' : ''}` : 'View Order Details'}>
                                        {/* {orderDate && (
                                            <div className="order-card-datetime-top-right">
                                                <div className="order-card-date">{formattedDate}</div>
                                                <div className="order-card-time">{formattedTime}</div>
                                            </div>
                                        )} */}
                                        <td data-label="Order #">
                                            <Link to={`/orders/${order.id}`} onClick={handleLinkClick}>{order.bigcommerce_order_id || order.id}</Link>
                                            {/* This status badge is for mobile view, hidden on desktop */}
                                            <span className={`order-status-badge-table status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')} hide-on-desktop`}>{order.status || 'Unknown'}</span>
                                        </td>
                                        <td data-label="Order Date" className="mobile-order-date-cell">{formattedDate}</td>
                                        <td data-label="Customer">{order.customer_company || order.customer_name || 'N/A'}</td>
                                        {/* This Status cell is for desktop view (hidden on mobile by .hide-mobile) */}
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

            {/* Sticky Button Wrapper */}
            <div className="ingest-controls-sticky-wrapper">
                <div className="ingest-controls">
                    {ingestionMessage && 
                        <div 
                            className="ingestion-message" 
                            style={{ 
                                color: ingestionMessage.toLowerCase().includes('error') || ingestionMessage.toLowerCase().includes('failed') ? 'var(--error-text)' : 'var(--success-text)',
                                marginRight: '15px', 
                                alignSelf: 'center',
                                fontWeight: 500
                            }}>
                            {ingestionMessage}
                        </div>
                    }
                    <button onClick={handleIngestOrders} disabled={ingesting} className="ingest-button">
                        {ingesting ? 'Importing...' : 'IMPORT NEW ORDERS'}
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;
// --- END OF FILE Dashboard.jsx ---
