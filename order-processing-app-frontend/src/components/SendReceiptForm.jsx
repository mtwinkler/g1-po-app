// frontend/src/components/SendReceiptForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext'; // Adjust path if needed
import './SendReceiptForm.css'; // Create this CSS file, can import FormCommon.css

function SendReceiptForm() {
    const { orderId } = useParams();
    const navigate = useNavigate();
    const { currentUser, apiService, loading: authLoading } = useAuth(); // Make sure apiService is exposed by your AuthContext
    const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

    const [orderSummary, setOrderSummary] = useState(null);
    const [customerEmail, setCustomerEmail] = useState('');
    const [loading, setLoading] = useState(true);
    const [formError, setFormError] = useState(null);
    const [successMessage, setSuccessMessage] = useState('');
    const [isSending, setIsSending] = useState(false);

    const fetchOrderSummary = useCallback(async (signal) => {
        if (!currentUser || !orderId) {
            setLoading(false);
            return;
        }
        setLoading(true);
        setFormError(null);
        try {
            // Fetch just enough order details for summary and email
            // The get_order_details endpoint from orders.py should work well
            const orderDetails = await apiService.get(`/orders/${orderId}`, {}, { signal });
            
            if (signal.aborted) return;

            if (orderDetails && orderDetails.order) {
                setOrderSummary({
                    bigcommerceOrderId: orderDetails.order.bigcommerce_order_id,
                    customerName: orderDetails.order.customer_name || orderDetails.order.customer_company || 'N/A',
                    orderDate: orderDetails.order.order_date,
                    totalSalePrice: orderDetails.order.total_sale_price
                });
                // Use customer_email from the main order record, which should be populated during ingestion
                setCustomerEmail(orderDetails.order.customer_email || '');
            } else {
                setFormError('Order not found or details are missing.');
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('Error fetching order summary:', err);
                setFormError(err.message || 'Failed to fetch order summary.');
            }
        } finally {
            if (!signal || !signal.aborted) setLoading(false);
        }
    }, [orderId, currentUser, apiService]);

    useEffect(() => {
        if (authLoading) return; // Wait for auth state to be determined
        if (!currentUser) {
            navigate('/login'); // Redirect if not logged in
            return;
        }
        const abortController = new AbortController();
        fetchOrderSummary(abortController.signal);
        return () => abortController.abort();
    }, [orderId, currentUser, authLoading, navigate, fetchOrderSummary]);

    const handleEmailChange = (e) => {
        setCustomerEmail(e.target.value);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!customerEmail.trim()) {
            setFormError('Recipient email address is required.');
            return;
        }
        if (!/\S+@\S+\.\S+/.test(customerEmail)) {
            setFormError('Please enter a valid email address.');
            return;
        }

        setIsSending(true);
        setFormError(null);
        setSuccessMessage('');

        try {
            const responseData = await apiService.post(`/orders/${orderId}/send-receipt`, { email: customerEmail });
            setSuccessMessage(responseData.message || 'Paid invoice sent successfully!');
            setTimeout(() => {
                // Optionally navigate back to dashboard or order detail
                navigate('/dashboard'); // Or navigate(-1) to go back
            }, 2000);
        } catch (err) {
            console.error('Error sending receipt:', err);
            setFormError(err.message || err.data?.error || err.data?.details || 'Failed to send paid invoice. Please try again.');
        } finally {
            setIsSending(false);
        }
    };

    if (loading || authLoading) {
        return <div className="form-page-container"><div className="form-message loading">Loading order details...</div></div>;
    }

    if (formError && !orderSummary) { // If initial load failed to get order summary
        return (
            <div className="form-page-container">
                <h2>Send Paid Invoice</h2>
                <div className="form-message error">{formError}</div>
                <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>
            </div>
        );
    }
    
    if (!orderSummary) {
         return (
            <div className="form-page-container">
                <h2>Send Paid Invoice</h2>
                <div className="form-message error">Order details could not be loaded.</div>
                <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>
            </div>
        );
    }


    return (
        <div className="form-page-container">
            <h2>Send Paid Invoice for Order #{orderSummary.bigcommerceOrderId}</h2>
            <Link to={`/orders/${orderId}`} className="form-back-link" style={{ marginRight: '20px' }}>← Back to Order Detail</Link>
            <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>

            <div className="order-summary-card">
                <h3>Order Summary</h3>
                <p><strong>Order #:</strong> {orderSummary.bigcommerceOrderId}</p>
                <p><strong>Customer:</strong> {orderSummary.customerName}</p>
                <p><strong>Order Date:</strong> {orderSummary.orderDate ? new Date(orderSummary.orderDate).toLocaleDateString() : 'N/A'}</p>
                <p><strong>Total:</strong> {orderSummary.totalSalePrice ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(orderSummary.totalSalePrice) : 'N/A'}</p>
            </div>

            {formError && <div className="form-message error" style={{ marginTop: '15px' }}>{formError}</div>}
            {successMessage && <div className="form-message success" style={{ marginTop: '15px' }}>{successMessage}</div>}

            <form onSubmit={handleSubmit} style={{ marginTop: '20px' }}>
                <div className="form-group">
                    <label htmlFor="customerEmail">Recipient Email:</label>
                    <input
                        type="email"
                        id="customerEmail"
                        name="customerEmail"
                        value={customerEmail}
                        onChange={handleEmailChange}
                        required
                        disabled={isSending}
                    />
                </div>
                <div className="form-actions">
                    <button type="submit" className="form-button primary" disabled={isSending}>
                        {isSending ? 'Sending...' : 'Send Paid Invoice'}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default SendReceiptForm;