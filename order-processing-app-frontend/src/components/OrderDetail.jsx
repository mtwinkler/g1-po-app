// OrderDetail.jsx (Refactored Controller)
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import './OrderDetail.css'; // Assuming this still holds common styles
import { useAuth } from '../contexts/AuthContext';
import DomesticOrderProcessor from './DomesticOrderProcessor';
import InternationalOrderProcessor from './InternationalOrderProcessor';

// Helper functions (createBrokerbinLink, formatShippingMethod, formatPaymentMethod, ProfitDisplay)
// ... (Keep all your existing helper functions: createBrokerbinLink, formatShippingMethod, formatPaymentMethod, ProfitDisplay)
const createBrokerbinLink = (partNumber) => {
  if (!partNumber) return '#';
  const trimmedPartNumber = String(partNumber).trim();
  if (!trimmedPartNumber) return '#';
  const encodedPartNumber = encodeURIComponent(trimmedPartNumber);
  return `https://members.brokerbin.com/partkey?login=g1tech&parts=${encodedPartNumber}`;
};

const formatShippingMethod = (methodString) => {
  if (!methodString || typeof methodString !== 'string') {
    return 'N/A';
  }
  const lowerMethod = methodString.toLowerCase().trim();

  if (lowerMethod.includes('fedex')) {
    if (lowerMethod.includes('ground')) return 'FedEx Ground';
    if (lowerMethod.includes('2day') || lowerMethod.includes('2 day')) return 'FedEx 2Day';
    if (lowerMethod.includes('priority overnight')) return 'FedEx Priority Overnight';
    if (lowerMethod.includes('standard overnight')) return 'FedEx Standard Overnight';
  }

  if (lowerMethod.includes('next day air early a.m.') || lowerMethod.includes('next day air early am') || lowerMethod.includes('next day air e')) return 'UPS Next Day Air Early A.M.';
  if (lowerMethod.includes('next day air')) return 'UPS Next Day Air';
  if (lowerMethod.includes('2nd day air') || lowerMethod.includes('second day air')) return 'UPS 2nd Day Air';
  
  if (lowerMethod.includes('worldwide express plus')) return 'UPS Worldwide Express Plus';
  if (lowerMethod.includes('worldwide express')) return 'UPS Worldwide Express';
  if (lowerMethod.includes('worldwide expedited')) return 'UPS Worldwide Expedited';
  if (lowerMethod.includes('worldwide saver')) return 'UPS Worldwide Saver';

  if (lowerMethod.includes('ups standard') || lowerMethod.includes('ups standard®') || lowerMethod.includes('ups standard℠')) {
    return 'UPS Standard';
  }
  if (lowerMethod.includes('standard') && lowerMethod.includes('ups') && !lowerMethod.includes('overnight')) {
      return 'UPS Standard';
  }
  
  if (lowerMethod.includes('ground') && lowerMethod.includes('ups')) return 'UPS Ground';
  if (lowerMethod.includes('ground') && !lowerMethod.includes('fedex')) return 'UPS Ground';
  if (lowerMethod.includes('free shipping')) return 'UPS Ground';

  const bcMatch = methodString.match(/\(([^)]+)\)/);
  if (bcMatch && bcMatch[1]) {
    const extracted = bcMatch[1].trim();
    const innerFormatted = formatShippingMethod(extracted);
    return innerFormatted !== 'N/A' && innerFormatted.toLowerCase() !== extracted.toLowerCase() ? innerFormatted : extracted;
  }

  return String(methodString).trim() || 'N/A';
};

const formatPaymentMethod = (paymentMethodString) => {
  if (typeof paymentMethodString !== 'string') {
    return 'N/A'; 
  }
  const bracketIndex = paymentMethodString.indexOf(" [");
  if (bracketIndex !== -1) {
    return paymentMethodString.substring(0, bracketIndex);
  }
  return paymentMethodString;
};


const ProfitDisplay = ({ info }) => {
    if (!info || !info.isCalculable) {
        return null;
    }
    const formatCurrency = (value) => {
        const numValue = Number(value);
        if (isNaN(numValue)) {
            return 'N/A';
        }
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(numValue);
    };
    const profitAmount = Number(info.profitAmount);
    const isProfitable = !isNaN(profitAmount) && profitAmount >= 0;
    const cardStyle = { backgroundColor: isProfitable ? 'rgba(40, 167, 69, 0.6)' : 'rgba(220, 53, 69, 0.6)' };
    const profitAmountColor = isProfitable ? 'var(--success-text)' : 'var(--error-text)';

    return (
        <div className="profit-display-card card" style={cardStyle}>
            <h3>Profitability Analysis</h3>
            <div className="profit-grid">
                <span>Revenue:</span><span>{formatCurrency(info.totalRevenue)}</span>
                <span>Cost:</span><span>{formatCurrency(info.totalCost)}</span>
                <hr style={{ gridColumn: '1 / -1', border: 'none', borderTop: '1px solid #ccc', margin: '12px 0' }} />
                <div style={{ textAlign: 'center' }}><div style={{ fontWeight: 'bold' }}>Profit:</div><div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>{formatCurrency(info.profitAmount)}</div></div>
                <div style={{ textAlign: 'center' }}><div style={{ fontWeight: 'bold' }}>Margin:</div><div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>{isNaN(Number(info.profitMargin)) ? 'N/A' : Number(info.profitMargin).toFixed(2)}%</div></div>
            </div>
        </div>
    );
};


function OrderDetail() {
  const { orderId } = useParams();
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const navigate = useNavigate();

  // ... (all your existing state variables in OrderDetail.jsx)
  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processSuccess, setProcessSuccess] = useState(false); 
  const [processSuccessMessage, setProcessSuccessMessage] = useState('');
  const [processedPOsInfo, setProcessedPOsInfo] = useState([]);
  const [processError, setProcessError] = useState(null);
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');
  const [manualStatusUpdateInProgress, setManualStatusUpdateInProgress] = useState(false);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [seeQuotesStatus, setSeeQuotesStatus] = useState('');
  const [lineItemSpares, setLineItemSpares] = useState({});
  const [loadingSpares, setLoadingSpares] = useState(false);
  const [processedOrderProfitInfo, setProcessedOrderProfitInfo] = useState({
    totalRevenue: 0, totalCost: 0, profitAmount: 0, profitMargin: 0, isCalculable: false
  });

  const componentSpecificStyles = `
    :root { /* ... */ } .order-detail-container h3 { /* ... */ } @media (prefers-color-scheme: dark) { /* ... */ }
  `; // Keeping this concise as it's unchanged

  // ... (fetchOrderAndSuppliers, useEffects, handleCopyToClipboard, handlePartNumberLinkClick, handleManualStatusUpdate, handleSeeQuotesClick - KEEP ALL THESE UNCHANGED)
  const fetchOrderAndSuppliers = useCallback(async (signal, isPostProcessRefresh = false) => {
    if (!currentUser) {
        setLoading(false); setOrderData(null); setSuppliers([]); return;
    }
    if (!isPostProcessRefresh) { 
      setLoading(true);
    }
    setError(null);
    if (!isPostProcessRefresh) {
        setProcessSuccess(false);
        setProcessError(null);
    }
    setStatusUpdateMessage('');

    try {
        const [fetchedOrderData, fetchedSuppliersData] = await Promise.all([
            apiService.get(`/orders/${orderId}`),
            apiService.get(`/suppliers`)
        ]);
        if (signal?.aborted) return;

        setOrderData(fetchedOrderData); 
        setSuppliers(fetchedSuppliersData || []);

        if (!isPostProcessRefresh) {
          setLineItemSpares({});
        }

        if (fetchedOrderData?.order?.status?.toLowerCase() === 'processed' && 
            fetchedOrderData.order.hasOwnProperty('actual_cost_of_goods_sold')) {
            
            let calculatedItemsRevenue = 0;
            if (fetchedOrderData.line_items && fetchedOrderData.line_items.length > 0) {
                calculatedItemsRevenue = fetchedOrderData.line_items.reduce((sum, item) => {
                    const price = parseFloat(item.sale_price || 0);
                    const quantity = parseInt(item.quantity || 0, 10);
                    return sum + (price * quantity);
                }, 0);
            }
            const revenue = calculatedItemsRevenue;
            const cost = parseFloat(fetchedOrderData.order.actual_cost_of_goods_sold || 0);
            const profit = revenue - cost;
            const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
            setProcessedOrderProfitInfo({
                totalRevenue: revenue,
                totalCost: cost,
                profitAmount: profit,
                profitMargin: margin,
                isCalculable: true
            });
        } else {
            setProcessedOrderProfitInfo({ isCalculable: false, totalRevenue: 0, totalCost: 0, profitAmount: 0, profitMargin: 0 });
        }

    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error in fetchOrderAndSuppliers:", err);
        setError(err.data?.message || err.message || "An unknown error occurred fetching data.");
      }
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, currentUser, apiService]);

  useEffect(() => {
    if (authLoading) { setLoading(true); return; }
    const abortController = new AbortController();
    if (orderId && currentUser && apiService) {
        fetchOrderAndSuppliers(abortController.signal, false);
    }
    else if (!currentUser && !authLoading && orderId) { setLoading(false); setError("Please log in."); }
    else if (!orderId) { setError("Order ID missing."); setLoading(false); }
    return () => abortController.abort();
  }, [orderId, currentUser, authLoading, fetchOrderAndSuppliers, apiService]);

  useEffect(() => {
    if (!currentUser || !orderData?.line_items || orderData.line_items.length === 0 || !apiService) return;
    const fetchAllSpares = async () => {
        setLoadingSpares(true);
        const sparesMap = {};
        for (const item of orderData.line_items) {
            if (item.original_sku && item.hpe_pn_type === 'option') {
                try {
                    const trimmedOriginalSku = String(item.original_sku).trim();
                    if (!trimmedOriginalSku) continue;
                    const spareData = await apiService.get(`/lookup/spare_part/${encodeURIComponent(trimmedOriginalSku)}`);
                    if (spareData.spare_sku) sparesMap[item.line_item_id] = String(spareData.spare_sku).trim();
                } catch (err) {
                    if (err.status !== 404) console.error(`Spare lookup exception for ${item.original_sku}:`, err);
                }
            }
        }
        setLineItemSpares(sparesMap); setLoadingSpares(false);
    };
    fetchAllSpares();
  }, [orderData?.line_items, currentUser, apiService]);

  const handleCopyToClipboard = async (textToCopy) => {
    if (!textToCopy) return;
    try {
        await navigator.clipboard.writeText(String(textToCopy).trim());
        setClipboardStatus(`Copied: ${String(textToCopy).trim()}`);
        setTimeout(() => setClipboardStatus(''), 1500);
    } catch (err) {
        console.error('Clipboard write failed:', err);
        setClipboardStatus('Failed to copy!');
        setTimeout(() => setClipboardStatus(''), 1500);
    }
  };
  
  const handlePartNumberLinkClick = async (e, partNumber) => {
    e.preventDefault();
    if (orderData?.order?.bigcommerce_order_id) {
        await handleCopyToClipboard(orderData.order.bigcommerce_order_id);
    }
    if (!currentUser || !apiService) {
        setStatusUpdateMessage("Please log in to perform this action or API service is unavailable.");
        return;
    }
    const currentOrderStatus = orderData?.order?.status?.toLowerCase();
    const trimmedPartNumberForStatusCheck = String(partNumber || '').trim();
    if (currentOrderStatus === 'new' && trimmedPartNumberForStatusCheck) {
      try {
        setStatusUpdateMessage('');
        await apiService.post(`/orders/${orderId}/status`, { status: 'RFQ Sent' });
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, false); 
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${trimmedPartNumberForStatusCheck}`);
      } catch (err) {
        let errorMsg = err.data?.message || err.message || `Error updating status for part ${trimmedPartNumberForStatusCheck}`;
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setStatusUpdateMessage(errorMsg);
      }
    }
    const brokerbinUrl = createBrokerbinLink(partNumber);
    window.open(brokerbinUrl, '_blank', 'noopener,noreferrer');
  };

  const handleManualStatusUpdate = async (newStatus) => {
    if (!currentUser || !apiService) { setStatusUpdateMessage("Please log in or API service unavailable."); return; }
    if (!orderId) { setStatusUpdateMessage("Order ID missing."); return; }
    setManualStatusUpdateInProgress(true); setStatusUpdateMessage('');
    try {
        await apiService.post(`/orders/${orderId}/status`, { status: newStatus });
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal, false); 
    } catch (err) {
        let errorMsg = err.data?.message || err.message || "Error updating status.";
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setStatusUpdateMessage(errorMsg);
    } finally { setManualStatusUpdateInProgress(false); }
  };

  const handleSeeQuotesClick = async () => {
    if (!orderData?.order?.bigcommerce_order_id) {
      setSeeQuotesStatus('Error: Order number not available.');
      setTimeout(() => setSeeQuotesStatus(''), 3000);
      return;
    }
    const orderNumber = orderData.order.bigcommerce_order_id;
    const searchPhrase = `Show me, in list format, the quoted prices received only today for Brokerbin RFQ and order number ${orderNumber}. Also include any comments included with the quotes. Disregard anything below "From: Global One Technology" in the emails. Note that "ea" is an abbreviation for each.`;
    try {
      await navigator.clipboard.writeText(searchPhrase);
      setSeeQuotesStatus(`Gemini prompt copied!`);
      setTimeout(() => setSeeQuotesStatus(''), 3000);
    } catch (err) {
      console.error('Failed to copy search phrase to clipboard:', err);
      setSeeQuotesStatus('Error: Could not copy to clipboard. Please try manually.');
      setTimeout(() => setSeeQuotesStatus(''), 5000);
    }
  };

  if (authLoading) return <div className="loading-message">Loading session...</div>;
  if (!currentUser && !authLoading) return <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}><h2>Order Details</h2><p className="error-message">Please <Link to="/login">log in</Link>.</p></div>;
  if (loading && !orderData) return <div className="loading-message">Loading order details...</div>;
  if (error && !loading) return <div className="error-message" style={{ margin: '20px', padding: '20px', border: '1px solid red' }}>Error: {error}</div>;
  
  const order = orderData?.order;
  const lineItems = orderData?.line_items || [];
  const orderStatus = order?.status?.toLowerCase();
  const isActuallyProcessed = orderStatus === 'processed' || orderStatus === 'completed offline';
  const canDisplayProcessingForms = !processSuccess && !isActuallyProcessed;

  if (!order && !processSuccess && !loading) {
      return <p style={{ textAlign: 'center', marginTop: '20px' }}>Order details not found or error loading.</p>;
  }
  
  let displayOrderDate = 'N/A';
  if (order?.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) { /* ignore */ }

  const displayShipMethodInOrderInfo = formatShippingMethod(
    (order?.is_bill_to_customer_account && order?.customer_selected_freight_service) 
        ? order.customer_selected_freight_service
        : (order?.is_bill_to_customer_fedex_account && order?.customer_selected_fedex_service) 
            ? order.customer_selected_fedex_service
            : order?.customer_shipping_method 
  );

  const isInternationalOrder = order?.is_international && order?.customer_shipping_country_iso2 !== 'US';

  return (
    <div className="order-detail-container">
      <style>{componentSpecificStyles}</style>
      <div className="order-title-section">
        <h2>
          <span>Order #{order?.bigcommerce_order_id || orderId} </span>
          <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order?.bigcommerce_order_id)} className="copy-button" disabled={!order?.bigcommerce_order_id}>📋</button>
          {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
        </h2>
        {order && (
            <span className={`order-status-badge status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
            {order.status || 'Unknown'}
            </span>
        )}
      </div>

      {statusUpdateMessage && !processSuccess && (
          <div className={statusUpdateMessage.toLowerCase().includes("error") ? "error-message" : "success-message"} style={{ marginTop: '10px', marginBottom: '10px' }}>
              {statusUpdateMessage}
          </div>
      )}
      
      {processError && !processSuccess && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}
      
      {processSuccess && (
        <div className="process-success-container card">
          <p className="success-message-large">ORDER PROCESSED SUCCESSFULLY!</p>
           {orderStatus === 'processed' && !(orderData?.order?.g1_onsite_fulfillment_mode) && processedOrderProfitInfo.isCalculable && (
             <ProfitDisplay info={processedOrderProfitInfo} />
           )}
        </div>
      )}
      
      {/* This ProfitDisplay shows when page loads and order is already processed */}
      {orderStatus === 'processed' && !processSuccess && !(orderData?.order?.g1_onsite_fulfillment_mode) && processedOrderProfitInfo.isCalculable && (
        <ProfitDisplay info={processedOrderProfitInfo} />
      )}


      {orderData?.order?.status?.toLowerCase() === 'rfq sent' && orderData?.order?.bigcommerce_order_id && !isActuallyProcessed && !processSuccess && (
        <section className="see-quotes-gmail-card card">
         <div className="button-container-center">
            <button
              onClick={handleSeeQuotesClick}
              className="btn btn-primary"
              disabled={manualStatusUpdateInProgress}
            >
              View Supplier Quotes Received
            </button>
          </div>
          {seeQuotesStatus && (
            <p className={`clipboard-status ${seeQuotesStatus.toLowerCase().includes('error') ? 'error-message-inline' : 'success-message-inline'} centered-status-message`}>
              {seeQuotesStatus}
            </p>
          )}
        </section>
      )}

      {orderData && order && !processSuccess && !isActuallyProcessed && (
       <section className="order-info card">
        <h3>Order Information</h3>
        <div><strong>Rec'd:</strong> {displayOrderDate}</div>
        <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
        <div><strong>Paid by:</strong> {formatPaymentMethod(order.payment_method || 'N/A')}</div>
        <div><strong>Ship via:</strong> {displayShipMethodInOrderInfo}</div>
        <div><strong>Ship to:</strong> {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'} ({order.customer_shipping_country_iso2 || 'N/A'})</div>

        {order.is_bill_to_customer_account && order.customer_ups_account_number && (
          <div className="customer-ups-account-info" style={{backgroundColor: 'var(--info-bg,rgb(255, 0, 0))', color: 'var(--info-text,rgb(255, 255, 255))', border: '1px dashed var(--info-border, #b3e0ff)', opacity: '60%'}}>
            <strong>Bill Shipping To:</strong> Customer UPS Acct # {order.customer_ups_account_number}
            {order.customer_selected_freight_service && ` (Service: ${formatShippingMethod(order.customer_selected_freight_service)})`}
            {order.customer_ups_account_zipcode && ` (Zip: ${order.customer_ups_account_zipcode})`}
          </div>
        )}
         {order.is_bill_to_customer_fedex_account && order.customer_fedex_account_number && (
          <div className="customer-ups-account-info" style={{backgroundColor: 'var(--info-bg-alt,rgb(255, 0, 0))', color: 'var(--info-text-alt,rgb(255, 255, 255))', border: '1px dashed var(--info-border-alt, #b3ffcc)', opacity: '60%'}}>
            <strong>Bill Shipping To:</strong> Customer FedEx Acct # {order.customer_fedex_account_number}
            {order.customer_selected_fedex_service && ` (Service: ${formatShippingMethod(order.customer_selected_fedex_service)})`}
          </div>
        )}
        {order.customer_notes && (<div style={{ marginTop: '5px' }}><strong>Comments:</strong> {order.customer_notes}</div>)}
        <hr style={{ margin: '10px 0' }} />
        {lineItems.map((item) => (
            <p key={`orig-item-${item.line_item_id}`} className="order-info-sku-line">
                <span>({item.quantity || 0}) </span>
                <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.original_sku}`} onClick={(e) => handlePartNumberLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>
                {loadingSpares && item.hpe_pn_type === 'option' && !lineItemSpares[item.line_item_id] && <span className="loading-text"> (loading spare...)</span>}
                {lineItemSpares[item.line_item_id] && ( <span style={{ fontStyle: 'italic', marginLeft: '5px' }}>(<a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handlePartNumberLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a>)</span> )}
                {item.hpe_option_pn && String(item.hpe_option_pn).trim() !== String(item.original_sku).trim() && String(item.hpe_option_pn).trim() !== lineItemSpares[item.line_item_id] && (<span>{'('} <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handlePartNumberLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a>{')'}</span>)}
                <span> ${parseFloat(item.sale_price || 0).toFixed(2)}</span>
            </p>
        ))}
      </section>
      )}

      {orderData && order && canDisplayProcessingForms && (
        isInternationalOrder ? (
          <InternationalOrderProcessor
            orderData={orderData}
            suppliers={suppliers}
            apiService={apiService}
            setProcessError={setProcessError}
            onSuccessRefresh={() => fetchOrderAndSuppliers(null, true)}
          />
        ) : (
          <DomesticOrderProcessor
            orderData={orderData}
            suppliers={suppliers}
            apiService={apiService}
            fetchOrderAndSuppliers={fetchOrderAndSuppliers}
            setProcessSuccess={setProcessSuccess}
            setProcessSuccessMessage={setProcessSuccessMessage}
            setProcessedPOsInfo={setProcessedPOsInfo}
            setProcessError={setProcessError}
          />
        )
      )}
      
      <div className="manual-actions-section" style={{marginTop: "20px"}}>
           {order && (order.status?.toLowerCase() === 'pending') && !isActuallyProcessed && !processSuccess &&(
              <button onClick={() => handleManualStatusUpdate('Completed Offline')} className="manual-action-button button-mark-completed" disabled={manualStatusUpdateInProgress}>
                  {manualStatusUpdateInProgress ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
           {order && order.status?.toLowerCase() === 'new' && !isActuallyProcessed && !processSuccess && (
              <div style={{ marginTop: '10px', textAlign: 'center' }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); if (!manualStatusUpdateInProgress) handleManualStatusUpdate('pending');}}
                      className={`link-button ${manualStatusUpdateInProgress ? 'link-button-updating' : ''}`}
                      style={{ fontSize: '0.9em', color: !manualStatusUpdateInProgress ? 'var(--text-secondary)' : undefined }}
                      aria-disabled={manualStatusUpdateInProgress}>
                      {manualStatusUpdateInProgress ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                  </a>
              </div>
          )}
      </div>

      <div className="order-actions" style={{ marginTop: '20px', textAlign: 'center' }}>
          {/* Send Receipt Button Uses the new class */}
                {orderStatus === 'processed' && !processSuccess && (
                    <button
                        onClick={() => navigate(`/orders/${orderId}/send-receipt-form`)}
                        className="send-paid-invoice-button" 
                        style={{ marginRight: '10px' }} 
                        title="Send Paid Invoice / Receipt to Customer"
                    >
                        Send Paid Invoice
                    </button>
                )}

                {/* NEW Send Wire Transfer Invoice Button */}
                {orderStatus === 'unpaid/not invoiced' && !processSuccess && (
                    <button
                        onClick={() => navigate(`/orders/${orderId}/send-wire-invoice-form`)}
                        className="btn btn-warning btn-sm" // Example: different color for this action
                        style={{ marginRight: '10px' }}
                        title="Send Wire Transfer Invoice to Customer"
                    >
                        Send Wire Invoice
                    </button>
                )}

                {(isActuallyProcessed || processSuccess) && (
                    <button type="button" onClick={() => navigate('/dashboard')} className="back-to-dashboard-button">
                        BACK TO DASHBOARD
                    </button>
                )}
                {isActuallyProcessed && !processSuccess && (
                    <div style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
                        This order has been {order?.status?.toLowerCase()} and no further automated actions are available.
                    </div>
                )}
            </div>
        </div>
    );
}

export default OrderDetail;