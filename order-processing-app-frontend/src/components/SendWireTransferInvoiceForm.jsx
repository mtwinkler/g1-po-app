// frontend/src/components/SendWireTransferInvoiceForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext'; // Adjust path if needed
import './SendReceiptForm.css'; // Can reuse SendReceiptForm.css or create a new one if styles differ significantly

function SendWireTransferInvoiceForm() {
    const { orderId } = useParams();
    const navigate = useNavigate();
    const { currentUser, apiService, loading: authLoading } = useAuth();

    const [orderSummary, setOrderSummary] = useState(null);
    const [customerEmail, setCustomerEmail] = useState('');
    const [addWireFee, setAddWireFee] = useState(true); // Default to checked (true)
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
            const orderDetails = await apiService.get(`/orders/${orderId}`, {}, { signal });
            
            if (signal.aborted) return;

            if (orderDetails && orderDetails.order) {
                setOrderSummary({
                    bigcommerceOrderId: orderDetails.order.bigcommerce_order_id,
                    customerName: orderDetails.order.customer_name || orderDetails.order.customer_company || 'N/A',
                    orderDate: orderDetails.order.order_date,
                    totalSalePrice: orderDetails.order.total_sale_price, // This is the original total
                    paymentMethod: orderDetails.order.payment_method 
                });
                setCustomerEmail(orderDetails.order.customer_email || '');

                // Optionally, automatically check the "addWireFee" box if the payment method string indicates it,
                // though the user can still override it. This is a UX choice.
                // if (orderDetails.order.payment_method && orderDetails.order.payment_method.toLowerCase().includes('[$25 usd additional fee]')) {
                //    setAddWireFee(true);
                // }

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
        if (authLoading) return; 
        if (!currentUser) {
            navigate('/login'); 
            return;
        }
        const abortController = new AbortController();
        fetchOrderSummary(abortController.signal);
        return () => abortController.abort();
    }, [orderId, currentUser, authLoading, navigate, fetchOrderSummary]);

    const handleEmailChange = (e) => {
        setCustomerEmail(e.target.value);
    };

    const handleFeeChange = (e) => {
        setAddWireFee(e.target.checked);
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
            const payload = { 
                email: customerEmail, 
                add_wire_fee: addWireFee 
            };
            const responseData = await apiService.post(`/orders/${orderId}/send-wire-invoice`, payload);
            setSuccessMessage(responseData.message || 'Wire transfer invoice sent successfully!');
            setTimeout(() => {
                navigate(`/orders/${orderId}`); // Navigate back to order detail to see updated status
            }, 2500);
        } catch (err) {
            console.error('Error sending wire transfer invoice:', err);
            setFormError(err.message || err.data?.error || err.data?.details || 'Failed to send wire transfer invoice. Please try again.');
        } finally {
            setIsSending(false);
        }
    };

    if (loading || authLoading) {
        return <div className="form-page-container"><div className="form-message loading">Loading order details...</div></div>;
    }

    if (formError && !orderSummary) { 
        return (
            <div className="form-page-container">
                <h2>Send Wire Transfer Invoice</h2>
                <div className="form-message error">{formError}</div>
                <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>
            </div>
        );
    }
    
    if (!orderSummary) {
         return (
            <div className="form-page-container">
                <h2>Send Wire Transfer Invoice</h2>
                <div className="form-message error">Order details could not be loaded or order not found.</div>
                <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>
            </div>
        );
    }

    return (
        <div className="form-page-container"> {/* Uses styles from FormCommon.css via SendReceiptForm.css */}
            <h2>Send Wire Invoice for Order #{orderSummary.bigcommerceOrderId}</h2>
            <Link to={`/orders/${orderId}`} className="form-back-link" style={{ marginRight: '20px' }}>← Back to Order Detail</Link>
            <Link to="/dashboard" className="form-back-link">← Back to Dashboard</Link>

            <div className="order-summary-card"> {/* Defined in SendReceiptForm.css or similar */}
                <h3>Order Summary</h3>
                <p><strong>Order #:</strong> {orderSummary.bigcommerceOrderId}</p>
                <p><strong>Customer:</strong> {orderSummary.customerName}</p>
                <p><strong>Order Date:</strong> {orderSummary.orderDate ? new Date(orderSummary.orderDate).toLocaleDateString() : 'N/A'}</p>
                <p><strong>Original Total:</strong> {orderSummary.totalSalePrice ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(orderSummary.totalSalePrice) : 'N/A'}</p>
                <p><strong>Payment Method:</strong> {orderSummary.paymentMethod || 'N/A'}</p>
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

                <div className="form-group checkbox-group"> {/* Added checkbox-group for potential styling */}
                    <input
                        type="checkbox"
                        id="addWireFee"
                        name="addWireFee"
                        checked={addWireFee}
                        onChange={handleFeeChange}
                        disabled={isSending}
                        style={{ marginRight: '8px' }}
                    />
                    <label htmlFor="addWireFee" style={{ display: 'inline', fontWeight: 'normal' }}>
                        Add $25.00 Wire Transfer Bank Fee to Invoice?
                    </label>
                </div>

                <div className="form-actions">
                    <button type="submit" className="form-button primary" disabled={isSending}>
                        {isSending ? 'Sending...' : 'Email Wire Transfer Invoice'}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default SendWireTransferInvoiceForm;