// OrderDetail.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import './OrderDetail.css'; 
import { useAuth } from '../contexts/AuthContext';

// --- Helper function for debouncing ---
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);
  return debouncedValue;
}

// Helper function for Brokerbin links
const createBrokerbinLink = (partNumber) => {
  if (!partNumber) return '#';
  const encodedPartNumber = encodeURIComponent(partNumber);
  return `https://members.brokerbin.com/partkey?login=g1tech&parts=${encodedPartNumber}`;
};

// Helper to escape regex special characters
function escapeRegExp(string) {
  if (typeof string !== 'string') return '';
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const formatShippingMethod = (methodString) => {
  if (!methodString || typeof methodString !== 'string') {
    return 'N/A';
  }
  const match = methodString.match(/\(([^)]+)\)/);
  if (match && match[1]) {
    return match[1];
  }
  return methodString;
};


function OrderDetail() {
  const { orderId } = useParams();
  const { currentUser, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(null);
  const [processError, setProcessError] = useState(null);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');
  const [manualStatusUpdateInProgress, setManualStatusUpdateInProgress] = useState(false);

  const [selectedSupplierId, setSelectedSupplierId] = useState('');
  const [poNotes, setPoNotes] = useState('');
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [shipmentMethod, setShipmentMethod] = useState('');
  const [shipmentWeight, setShipmentWeight] = useState('');

  const setPurchaseItemsRef = useRef(setPurchaseItems);
  useEffect(() => { setPurchaseItemsRef.current = setPurchaseItems; }, []);
  const purchaseItemsRef = useRef(purchaseItems);
  useEffect(() => { purchaseItemsRef.current = purchaseItems; }, [purchaseItems]);

  const cleanPullSuffix = " - clean pull";

  const fetchOrderAndSuppliers = useCallback(async (signal) => {
    if (!currentUser) {
        setLoading(false);
        setOrderData(null);
        setSuppliers([]);
        return;
    }
    setLoading(true); setError(null); setProcessSuccess(null); setProcessError(null); setStatusUpdateMessage('');
    try {
        const token = await currentUser.getIdToken(true);
        const headers = { 'Authorization': `Bearer ${token}` };
        const orderApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}`;
        const suppliersApiUrl = `${VITE_API_BASE_URL}/suppliers`;

        const orderPromise = fetch(orderApiUrl, { signal, headers });
        const suppliersPromise = fetch(suppliersApiUrl, { signal, headers });
        const [orderResponse, suppliersResponse] = await Promise.all([orderPromise, suppliersPromise]);

        if (signal && signal.aborted) return;

        if (!orderResponse.ok) {
            let errorMsg = `Order fetch failed: ${orderResponse.status}`;
            if (orderResponse.status === 401 || orderResponse.status === 403) {
                errorMsg = "Unauthorized to fetch order. Your session might have expired.";
            } else {
                 try { const errorData = await orderResponse.json(); errorMsg = errorData.details || errorData.error || errorMsg; } catch (e) {}
            }
            throw new Error(errorMsg);
        }
        if (!suppliersResponse.ok) {
            let errorMsg = `Supplier fetch failed: ${suppliersResponse.status}`;
             if (suppliersResponse.status === 401 || suppliersResponse.status === 403) {
                errorMsg = "Unauthorized to fetch suppliers. Your session might have expired.";
            } else {
                try { const errorData = await suppliersResponse.json(); errorMsg = errorData.error || errorMsg; } catch (e) {}
            }
            throw new Error(errorMsg);
        }
        const fetchedOrderData = await orderResponse.json();
        const fetchedSuppliers = await suppliersResponse.json();

        if (signal && signal.aborted) return;

        setOrderData(fetchedOrderData);
        setSuppliers(fetchedSuppliers || []);

        if (fetchedOrderData?.order) {
            let defaultMethodForForm = 'UPS Ground';
            const customerMethodRaw = fetchedOrderData.order.customer_shipping_method;
            const parsedCustomerMethodForForm = formatShippingMethod(customerMethodRaw);
            if (parsedCustomerMethodForForm && typeof parsedCustomerMethodForForm === 'string') {
                const methodLower = parsedCustomerMethodForForm.toLowerCase();
                if (methodLower.includes('ground')) defaultMethodForForm = 'UPS Ground';
                else if (methodLower.includes('2nd day') || methodLower.includes('second day')) defaultMethodForForm = 'UPS 2nd Day Air';
                else if (methodLower.includes('next day') || methodLower.includes('nda')) defaultMethodForForm = 'UPS Next Day Air';
                else if (customerMethodRaw?.toLowerCase().includes('free shipping')) defaultMethodForForm = 'UPS Ground';
            }
            setShipmentMethod(defaultMethodForForm);
        }
        if (fetchedOrderData?.line_items) {
            const initialItems = fetchedOrderData.line_items.map(item => {
                const initialSku = item.hpe_option_pn || item.original_sku || '';
                let initialDescription = item.hpe_po_description || item.line_item_name || '';
                if (initialDescription && typeof initialDescription === 'string' && !initialDescription.endsWith(cleanPullSuffix)) initialDescription += cleanPullSuffix;
                else if (!initialDescription) initialDescription = cleanPullSuffix.trim();
                return {
                    original_order_line_item_id: item.line_item_id, sku: initialSku, description: initialDescription, skuInputValue: initialSku, quantity: item.quantity || 1, unit_cost: '', condition: 'New', original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn, original_name: item.line_item_name, hpe_po_description: item.hpe_po_description,
                };
            });
            setPurchaseItemsRef.current(initialItems);
        } else {
            setPurchaseItemsRef.current([]);
        }
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message || "An unknown error occurred fetching order data.");
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, cleanPullSuffix, VITE_API_BASE_URL, currentUser, navigate]);

  useEffect(() => {
    if (authLoading) { 
        setLoading(true); 
        return;
    }
    const abortController = new AbortController();
    if (orderId && currentUser) {
        fetchOrderAndSuppliers(abortController.signal);
    } else if (!currentUser && orderId) {
        setLoading(false); 
        setError("Please log in to view order details.");
    } else if (!orderId) {
        setError(new Error("Order ID is missing in the URL."));
        setLoading(false);
    }
    return () => abortController.abort();
  }, [orderId, currentUser, authLoading, fetchOrderAndSuppliers]);

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  useEffect(() => {
    if (!currentUser || !debouncedSku || skuToLookup.index === -1) return;
    const abortController = new AbortController();
    const fetchDescription = async () => {
      try {
        const token = await currentUser.getIdToken(true);
        const lookupApiUrl = `${VITE_API_BASE_URL}/lookup/description/${encodeURIComponent(debouncedSku)}`;
        const response = await fetch(lookupApiUrl, { signal: abortController.signal, headers: { 'Authorization': `Bearer ${token}` } });
        
        if (abortController.signal.aborted) return;

        if (response.ok) {
            const data = await response.json();
            if (abortController.signal.aborted) return;
            const currentItems = purchaseItemsRef.current;
            const updatedItems = [...currentItems];
            if (updatedItems[skuToLookup.index]?.sku === debouncedSku) { 
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) newDescription += cleanPullSuffix;
                else if (!newDescription) { 
                    const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDesc ? existingDesc + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) newDescription = cleanPullSuffix.trim(); 
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
                setPurchaseItemsRef.current(updatedItems);
            }
        } else if (response.status === 401 || response.status === 403) {
            console.error("Unauthorized to fetch SKU description.");
            setError(prevError => prevError ? prevError + " SKU lookup failed (unauthorized)." : "SKU lookup failed (unauthorized).");
        }
      } catch (error) { if (error.name !== 'AbortError') console.error("Error fetching description:", error); }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, VITE_API_BASE_URL, currentUser, navigate]);

  const handleSupplierChange = (e) => { setSelectedSupplierId(e.target.value); const sId = parseInt(e.target.value,10); const s = suppliers.find(sup=>sup.id===sId); setPoNotes(s?.defaultponotes || ''); };
  const handlePoNotesChange = (e) => setPoNotes(e.target.value);
  const handlePurchaseItemChange = (index, field, value) => { const items = [...purchaseItemsRef.current]; items[index]={...items[index], [field]:value}; if(field==='sku')setSkuToLookup({index,sku:value}); setPurchaseItemsRef.current(items);};
  const handleShipmentMethodChange = (e) => setShipmentMethod(e.target.value);
  const handleShipmentWeightChange = (e) => setShipmentWeight(e.target.value);
  const handleCopyToClipboard = async (textToCopy) => { if(!textToCopy)return; try{await navigator.clipboard.writeText(String(textToCopy)); setClipboardStatus(`Copied: ${textToCopy}`); setTimeout(()=>setClipboardStatus(''),1500);}catch(err){setClipboardStatus('Failed to copy!');setTimeout(()=>setClipboardStatus(''),1500);}};

  const handleBrokerbinLinkClick = async (e, partNumber) => {
    if (!currentUser) { setStatusUpdateMessage("Please log in to perform this action."); e.preventDefault(); return; }
    setStatusUpdateMessage('');
    if (orderData?.order?.status?.toLowerCase() === 'new') {
      try {
        const token = await currentUser.getIdToken(true);
        const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
        const response = await fetch(statusApiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ status: 'RFQ Sent' }) });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) { let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`; if(response.status===401||response.status===403) {err="Unauthorized. Please log in again."; navigate('/login');} throw new Error(err); }
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal); 
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${partNumber}`);
      } catch (err) { setStatusUpdateMessage(`Error updating status: ${err.message}`); }
    } else if (orderData?.order?.status && !['rfq sent', 'processed'].includes(orderData.order.status.toLowerCase())) {
      setStatusUpdateMessage(`Order status is not 'new'. Cannot update to RFQ Sent.`);
    }
  };

  const handleManualStatusUpdate = async (newStatus) => {
    if (!currentUser) { setStatusUpdateMessage("Please log in to update status."); return; }
    if (!orderId || !VITE_API_BASE_URL) { setStatusUpdateMessage("Configuration error."); return; }
    setManualStatusUpdateInProgress(true); setStatusUpdateMessage('');
    try {
        const token = await currentUser.getIdToken(true);
        const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
        const response = await fetch(statusApiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ status: newStatus }) });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) { let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`; if(response.status===401||response.status===403) {err="Unauthorized. Please log in again."; navigate('/login');} throw new Error(err); }
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal); 
    } catch (err) { setStatusUpdateMessage(`Error updating status: ${err.message}`);
    } finally { setManualStatusUpdateInProgress(false); }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault(); 
    if (!currentUser) { setProcessError("Please log in to process the order."); return; }
    setProcessing(true); setProcessError(null); setProcessSuccess(null); setStatusUpdateMessage('');
    if (!selectedSupplierId) { setProcessError("Please select a supplier."); setProcessing(false); return; }
    const weightFloat = parseFloat(shipmentWeight);
    if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight."); setProcessing(false); return; }
    let itemValidationError = null;
    const finalPurchaseItems = purchaseItemsRef.current.map((item, index) => {
        const quantityInt = parseInt(item.quantity,10); const costFloat = parseFloat(item.unit_cost);
        if(isNaN(quantityInt)||quantityInt<=0){itemValidationError=`Item #${index+1} (SKU: ${item.sku||'N/A'}): Quantity must be > 0.`; return null;}
        if(item.unit_cost===''||isNaN(costFloat)||costFloat<0){itemValidationError=`Item #${index+1} (SKU: ${item.sku||'N/A'}): Unit cost is invalid.`; return null;}
        if(!item.sku){itemValidationError=`Item #${index+1}: Purchase SKU is required.`; return null;}
        if(!item.description){itemValidationError=`Item #${index+1} (SKU: ${item.sku}): Description is required.`; return null;}
        return {original_order_line_item_id:item.original_order_line_item_id, sku:item.sku, description:item.description, quantity:quantityInt, unit_cost:costFloat.toFixed(2), condition:item.condition||'New'};
    }).filter(Boolean); 
    if(itemValidationError){setProcessError(itemValidationError); setProcessing(false); return;}
    if(finalPurchaseItems.length === 0){setProcessError("No valid line items for PO."); setProcessing(false); return;}
    try {
      const token = await currentUser.getIdToken(true);
      const payload = { supplier_id: parseInt(selectedSupplierId,10), payment_instructions:poNotes, total_shipment_weight_lbs:weightFloat, po_line_items:finalPurchaseItems };
      const processApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/process`;
      const response = await fetch(processApiUrl, { method: 'POST', headers: {'Content-Type':'application/json', 'Authorization':`Bearer ${token}`}, body: JSON.stringify(payload) });
      const responseData = await response.json().catch(()=>null);
      if (!response.ok) { let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`; if(response.status===401||response.status===403) {err="Unauthorized. Please log in again."; navigate('/login');} throw new Error(err); }
      setProcessSuccess(responseData.message || "Order processed successfully!");
      const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal); 
    } catch (err) { setProcessError(err.message || "An unexpected error occurred during processing.");
    } finally { setProcessing(false); }
  };

  if (authLoading) { 
    return <div className="loading-message">Loading session...</div>;
  }

  if (!currentUser) { 
    return (
        <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}>
            <h2>Order Details</h2>
            <p className="error-message">Please <Link to="/login">log in</Link> to view order details.</p>
        </div>
    );
  }

  if (loading && !orderData) {
    return <div className="loading-message">Loading order details...</div>;
  }

  if (error) { 
    return <div className="error-message">Error: {error}</div>;
  }

  if (!orderData || !orderData.order) { 
    return <p style={{textAlign: 'center', marginTop: '20px'}}>Order details not found or you may not have access.</p>;
  }

  const order = orderData.order;
  const originalLineItems = orderData.line_items || [];
  
  const isActuallyProcessed = order.status === 'Processed' || order.status === 'processed';
  const isActuallyCompletedOffline = order.status === 'Completed Offline' || order.status === 'completed offline';
  const isActuallyPending = order.status === 'Pending' || order.status === 'pending';
  const isActuallyInternational = order.status === 'international_manual'; 
  const isActuallyNew = order.status === 'New' || order.status === 'new';

  const canDisplayProcessOrderButton = !(isActuallyProcessed || isActuallyCompletedOffline || isActuallyPending || isActuallyInternational);
  const disableAllActions = processing || manualStatusUpdateInProgress; 
  const disableFormFields = isActuallyProcessed || isActuallyCompletedOffline || disableAllActions;


  let displayOrderDate = 'N/A';
  if (order.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) {}
  const displayCustomerShippingMethod = formatShippingMethod(order.customer_shipping_method);

  return (
    <div className="order-detail-container">
      <div className="order-title-section">
        <h2>
          <span>Order #{order.bigcommerce_order_id || 'N/A'} </span>
          <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order.bigcommerce_order_id)} className="copy-button" disabled={!order.bigcommerce_order_id}>📋</button>
          {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
        </h2>
        <span className={`order-status-badge status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
          {order.status || 'Unknown'}
        </span>
      </div>

      {statusUpdateMessage && !processError && !processSuccess && (<div className={statusUpdateMessage.toLowerCase().includes("error") ? "error-message" : "success-message"} style={{marginTop: '10px', marginBottom: '10px'}}>{statusUpdateMessage}</div>)}
      {processSuccess && <div className="success-message" style={{ marginBottom: '10px' }}>{processSuccess}</div>}
      {processError && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}

      <section className="order-info card">
         <h3>Order Information</h3>
        <div><strong>Rec'd:</strong> {displayOrderDate}</div>
        <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
        <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
        <div><strong>Ship:</strong> {displayCustomerShippingMethod} to {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>
        {order.customer_notes && ( <div style={{marginTop: '5px'}}><strong>Comments:</strong> {order.customer_notes}</div> )}
        <hr style={{margin: '10px 0'}}/>
        {originalLineItems.map((item, index) => (
            <div key={`orig-item-${item.line_item_id || index}`} className="order-info-item">
                <span>({item.quantity || 0})</span>
                <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.original_sku || ''}`} onClick={(e) => handleBrokerbinLinkClick(e, item.original_sku)}> {item.original_sku || 'N/A'} </a>
                {item.hpe_option_pn && item.hpe_option_pn !== item.original_sku && ( <span> {' ('} <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.hpe_option_pn || ''}`} onClick={(e) => handleBrokerbinLinkClick(e, item.hpe_option_pn)}> {item.hpe_option_pn} </a> {')'} </span> )}
                 <span> @ ${parseFloat(item.sale_price || 0).toFixed(2)}</span>
            </div>
        ))}
      </section>

      <div className="manual-actions-section"> {/* Removed inline styles, will be handled by CSS class if needed */}
          {order.status && (order.status.toLowerCase() === 'international_manual' || order.status.toLowerCase() === 'pending') && !isActuallyProcessed && !isActuallyCompletedOffline && (
              <button 
                onClick={() => handleManualStatusUpdate('Completed Offline')} 
                // MODIFIED: Apply global button classes
                className="btn btn-gradient btn-shadow-lift btn-success manual-action-button-specifics" 
                disabled={disableAllActions} 
              >
                  {manualStatusUpdateInProgress && (order.status.toLowerCase() === 'international_manual' || order.status.toLowerCase() === 'pending') ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
      </div>
      
      {canDisplayProcessOrderButton && (
          <form onSubmit={handleProcessOrder} className={`processing-form ${disableFormFields ? 'form-disabled' : ''}`}>
              <section className="purchase-info card">
                <h3>Purchase Information</h3>
                <div className="form-grid">
                  <label htmlFor="supplier">Supplier:</label>
                  <select id="supplier" value={selectedSupplierId} onChange={handleSupplierChange} required disabled={disableFormFields}><option value="">-- Select Supplier --</option>{(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name || 'Unnamed Supplier'}</option>))}</select>
                  <label htmlFor="poNotes">PO Notes:</label>
                  <textarea id="poNotes" value={poNotes} onChange={handlePoNotesChange} rows="3" disabled={disableFormFields}/>
                </div>
                <div className="purchase-items-grid">
                  <h4>Items to Purchase:</h4>
                   <div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                   {purchaseItems.map((item, index) => (
                      <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                          <div><label className="mobile-label" htmlFor={`sku-${index}`}>SKU:</label><input id={`sku-${index}`} type="text" value={item.sku || ''} onChange={(e) => handlePurchaseItemChange(index, 'sku', e.target.value)} placeholder="SKU" required disabled={disableFormFields} title={item.original_sku ? `Original: ${item.original_sku}`: ''} className="sku-input"/></div>
                          <div><label className="mobile-label" htmlFor={`desc-${index}`}>Desc:</label><textarea id={`desc-${index}`} value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableFormFields} className="description-textarea"/></div>
                          <div className="qty-cost-row">
                              <div><label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label><input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableFormFields} className="qty-input"/></div>
                              <div><label className="mobile-label" htmlFor={`price-${index}`}>Cost:</label><input id={`price-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableFormFields} className="price-input"/></div>
                          </div>
                      </div>
                   ))}
                </div>
              </section>
              <section className="shipment-info card">
                    <h3>Shipment Information</h3>
                     <div className="form-grid">
                        <label htmlFor="shipmentMethod">Method:</label>
                        <select id="shipmentMethod" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableFormFields} required><option value="UPS Ground">UPS Ground</option><option value="UPS 2nd Day Air">UPS 2nd Day Air</option><option value="UPS Next Day Air">UPS Next Day Air</option></select>
                        <label htmlFor="shipmentWeight">Weight (lbs):</label>
                        <input type="number" id="shipmentWeight" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required disabled={disableFormFields} />
                    </div>
              </section>

              <div className="order-actions"> 
                  <button
                      type="submit" 
                      disabled={disableAllActions || processing} 
                      // MODIFIED: Apply global button classes + a specific class for overrides
                      className="btn btn-gradient btn-shadow-lift btn-success process-order-button-specifics"
                  >
                      {processing ? 'Processing...' : 'PROCESS ORDER'}
                  </button>

                  {isActuallyNew && !isActuallyProcessed && !isActuallyCompletedOffline && (
                      <div style={{ marginTop: '10px', textAlign: 'center' }}> 
                          <a
                              href="#"
                              onClick={(e) => {
                                  e.preventDefault();
                                  if (!disableAllActions) { 
                                      handleManualStatusUpdate('pending');
                                  }
                              }}
                              className={`link-button ${manualStatusUpdateInProgress && isActuallyNew ? 'link-button-updating' : ''}`}
                              style={{ 
                                  fontSize: '0.9em', 
                                  color: !(manualStatusUpdateInProgress && isActuallyNew) ? 'var(--text-secondary)' : undefined 
                              }}
                              aria-disabled={disableAllActions || manualStatusUpdateInProgress}
                          >
                              {manualStatusUpdateInProgress && isActuallyNew ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                          </a>
                      </div>
                  )}
              </div>
          </form>
      )}

      <div className="order-actions" style={{ marginTop: '20px' }}> 
          {isActuallyProcessed && ( 
              <button
                  type="button" 
                  onClick={() => navigate('/')}
                  // MODIFIED: Apply global button classes + a specific class for overrides if needed
                  className="btn btn-gradient btn-shadow-lift btn-primary back-to-dashboard-button-specifics"
                  disabled={disableAllActions} 
              >
                  BACK TO DASHBOARD
              </button>
          )}

          {(isActuallyProcessed || isActuallyCompletedOffline) && !canDisplayProcessOrderButton && ( 
              <div style={{ textAlign: 'center', marginTop: '0px', color: 'var(--text-secondary)' }}> 
                  This order has been {order.status?.toLowerCase()} and no further automated actions are available. 
              </div> 
          )}
      </div>
       
    </div>
  );
}

export default OrderDetail;