// --- START OF FILE OrderDetail.jsx ---

// OrderDetail.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import './OrderDetail.css';

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
  if (typeof string !== 'string') return ''; // Add type check
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// --- NEW Helper function to format shipping method ---
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
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL; // Store in a variable for easier use

  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(null);
  const [processError, setProcessError] = useState(null);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');

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
    console.log("OrderDetail.jsx: fetchOrderAndSuppliers CALLED for orderId:", orderId);
    setLoading(true); setError(null); setOrderData(null); setProcessSuccess(null); setProcessError(null); setStatusUpdateMessage('');

    try {
        console.log("OrderDetail.jsx: Inside TRY block, attempting fetches...");
        const orderApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}`;
        const suppliersApiUrl = `${VITE_API_BASE_URL}/suppliers`;
        console.log("OrderDetail.jsx: Fetching order from:", orderApiUrl);
        console.log("OrderDetail.jsx: Fetching suppliers from:", suppliersApiUrl);

        const orderResponse = await fetch(orderApiUrl, { signal });
        console.log("OrderDetail.jsx: After fetch order attempt. Status:", orderResponse?.status);
        const suppliersResponse = await fetch(suppliersApiUrl, { signal });
        console.log("OrderDetail.jsx: After fetch suppliers attempt. Status:", suppliersResponse?.status);

        if (!orderResponse.ok) {
            let errorMsg = `Order fetch failed: ${orderResponse.status}`;
            try { const errorData = await orderResponse.json(); errorMsg = errorData.details || errorData.error || errorMsg; } catch (parseError) {}
            throw new Error(errorMsg);
        }
         if (!suppliersResponse.ok) {
            let errorMsg = `Supplier fetch failed: ${suppliersResponse.status}`;
            try { const errorData = await suppliersResponse.json(); errorMsg = errorData.error || errorMsg; } catch (parseError) { }
            throw new Error(errorMsg);
        }

        console.log("OrderDetail.jsx: Both fetches successful (status OK). Processing responses...");
        const fetchedOrderData = await orderResponse.json();
        console.log("OrderDetail.jsx: Fetched order data (parsed):", fetchedOrderData);
        
        const fetchedSuppliers = await suppliersResponse.json();
        console.log("OrderDetail.jsx: Fetched suppliers (parsed):", fetchedSuppliers);
        
        setOrderData(fetchedOrderData); 
        setSuppliers(fetchedSuppliers || []);

        console.log("OrderDetail.jsx: Initializing form state...");
        if (fetchedOrderData?.order) {
            let defaultMethodForForm = 'UPS Ground';
            const customerMethodRaw = fetchedOrderData.order.customer_shipping_method;
            const parsedCustomerMethodForForm = formatShippingMethod(customerMethodRaw); 

            if (parsedCustomerMethodForForm && typeof parsedCustomerMethodForForm === 'string') {
                const methodLower = parsedCustomerMethodForForm.toLowerCase();
                if (methodLower.includes('ground')) { defaultMethodForForm = 'UPS Ground'; }
                else if (methodLower.includes('2nd day') || methodLower.includes('second day')) { defaultMethodForForm = 'UPS 2nd Day Air'; }
                else if (methodLower.includes('next day') || methodLower.includes('nda')) { defaultMethodForForm = 'UPS Next Day Air'; }
                 else if (customerMethodRaw && typeof customerMethodRaw === 'string' && customerMethodRaw.toLowerCase().includes('free shipping')) {
                    defaultMethodForForm = 'UPS Ground';
                }
            }
            setShipmentMethod(defaultMethodForForm);
            console.log("OrderDetail.jsx: Initialized form's shipmentMethod to:", defaultMethodForForm);
        } else {
            console.warn("OrderDetail.jsx: No order data found in response to initialize shipment method.");
        }

        if (fetchedOrderData?.line_items) {
            const initialItems = fetchedOrderData.line_items.map(item => {
                const initialSku = item.hpe_option_pn || item.original_sku || '';
                let initialDescription = item.hpe_po_description || item.line_item_name || '';
                if (initialDescription && typeof initialDescription === 'string' && !initialDescription.endsWith(cleanPullSuffix)) { // Added type check
                    initialDescription += cleanPullSuffix;
                } else if (!initialDescription) { 
                    initialDescription = cleanPullSuffix.trim(); 
                }
                return {
                    original_order_line_item_id: item.line_item_id,
                    sku: initialSku, description: initialDescription, skuInputValue: initialSku,
                    quantity: item.quantity || 1, unit_cost: '', condition: 'New',
                    original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn,
                    original_name: item.line_item_name, hpe_po_description: item.hpe_po_description,
                };
            });
            setPurchaseItemsRef.current(initialItems); 
            console.log("OrderDetail.jsx: Initialized purchaseItems with suffix:", initialItems);
        } else {
            setPurchaseItemsRef.current([]); 
            console.warn("OrderDetail.jsx: No line_items found in response to initialize purchaseItems.");
        }
        console.log("OrderDetail.jsx: Form state initialization complete.");

    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('OrderDetail.jsx: Fetch aborted in fetchOrderAndSuppliers');
      } else {
        console.error("OrderDetail.jsx: fetchOrderAndSuppliers CATCH block triggered:", err);
        setError(err.message || "An unknown error occurred during data fetching.");
      }
    } finally {
        setLoading(false); 
        console.log("OrderDetail.jsx: fetchOrderAndSuppliers FINALLY block running.");
    }
  }, [orderId, cleanPullSuffix, VITE_API_BASE_URL]);

  useEffect(() => {
    console.log("OrderDetail.jsx: OrderDetail useEffect running. orderId from useParams:", orderId);
    const abortController = new AbortController();
    if (orderId) {
        fetchOrderAndSuppliers(abortController.signal);
    } else {
        console.error("OrderDetail.jsx: Order ID is missing or invalid from URL params.");
        setError(new Error("Order ID is missing in the URL."));
        setLoading(false);
    }
    return () => {
      console.log("OrderDetail.jsx: OrderDetail cleanup: Aborting fetch for orderId:", orderId);
      abortController.abort();
    };
  }, [orderId, fetchOrderAndSuppliers]); // fetchOrderAndSuppliers is memoized and includes VITE_API_BASE_URL in its deps

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  useEffect(() => {
    const abortController = new AbortController();
    const fetchDescription = async () => {
      if (debouncedSku && typeof debouncedSku === 'string' && skuToLookup.index !== -1) {
        const lookupApiUrl = `${VITE_API_BASE_URL}/lookup/description/${encodeURIComponent(debouncedSku)}`;
        console.log(`OrderDetail.jsx: Fetching description from: ${lookupApiUrl} for index: ${skuToLookup.index}`);
        try {
          const response = await fetch(lookupApiUrl, { signal: abortController.signal });
          if (response.ok) {
            const data = await response.json();
            const currentItems = purchaseItemsRef.current; 
            const updatedItems = [...currentItems]; // Create a new array

            if (updatedItems[skuToLookup.index] && updatedItems[skuToLookup.index].sku === debouncedSku) { 
                let newDescription = data.description; 
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) { // Added type check
                    newDescription += cleanPullSuffix;
                } else if (newDescription === null || newDescription === undefined || newDescription === "") { 
                    const existingDescWithoutSuffix = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDescWithoutSuffix ? existingDescWithoutSuffix + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) {
                        newDescription = cleanPullSuffix.trim();
                    }
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription }; // Create a new item object
                setPurchaseItemsRef.current(updatedItems); 
                console.log(`OrderDetail.jsx: Updated description for index ${skuToLookup.index} to: ${newDescription}`);
            } else {
                console.log(`OrderDetail.jsx: SKU changed again for index ${skuToLookup.index}, ignoring stale description fetch.`);
            }
          } else { console.error("OrderDetail.jsx: Description lookup failed:", response.status); }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('OrderDetail.jsx: Description fetch aborted');
            } else {
                console.error("OrderDetail.jsx: Error fetching description:", error);
            }
        }
      }
    };
    fetchDescription();
    return () => {
        console.log("OrderDetail.jsx: Cleanup for description fetch effect, SKU:", debouncedSku);
        abortController.abort();
    };
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, VITE_API_BASE_URL]);

  const handleSupplierChange = (e) => {
    const newSupplierId = e.target.value;
    setSelectedSupplierId(newSupplierId);
    const supplierIdInt = parseInt(newSupplierId, 10);
    const selectedSupplier = suppliers.find(s => s.id === supplierIdInt);
    let extractedNotes = '';
    if (selectedSupplier && selectedSupplier.defaultponotes !== null && selectedSupplier.defaultponotes !== undefined) {
        extractedNotes = selectedSupplier.defaultponotes;
    }
    setPoNotes(extractedNotes);
  };

  const handlePoNotesChange = (e) => { setPoNotes(e.target.value); };

  const handlePurchaseItemChange = (index, field, value) => {
    const currentItems = purchaseItemsRef.current; 
    const updatedItems = [...currentItems];
    const itemToUpdate = { ...updatedItems[index] }; // Create new object for the item
    itemToUpdate[field] = value; 
    
    if (field === 'sku') {
      setSkuToLookup({ index, sku: value });
    }
    updatedItems[index] = itemToUpdate;
    setPurchaseItemsRef.current(updatedItems); 
  };

  const handleShipmentMethodChange = (e) => { setShipmentMethod(e.target.value); };
  const handleShipmentWeightChange = (e) => { setShipmentWeight(e.target.value); };

  const handleCopyToClipboard = async (textToCopy) => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(String(textToCopy));
      setClipboardStatus(`Copied: ${textToCopy}`);
      setTimeout(() => setClipboardStatus(''), 1500);
    } catch (err) {
      console.error('Failed to copy:', err);
      setClipboardStatus('Failed to copy!');
      setTimeout(() => setClipboardStatus(''), 1500);
    }
  };

  const handleBrokerbinLinkClick = async (e, partNumber) => {
    setStatusUpdateMessage('');
    if (orderData?.order?.status && typeof orderData.order.status === 'string' && orderData.order.status.toLowerCase() === 'new') {
      console.log(`OrderDetail.jsx: Brokerbin link clicked for ${partNumber}. Order status is 'new'. Attempting to update status to 'RFQ Sent'.`);
      const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
      console.log("OrderDetail.jsx: Updating status via:", statusApiUrl);
      try {
        const response = await fetch(statusApiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'RFQ Sent' }),
        });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(responseData?.details || responseData?.error || `HTTP error! Status: ${response.status}`);
        }
        setOrderData(prevData => ({
          ...prevData,
          order: { ...prevData.order, status: 'RFQ Sent' }
        }));
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${partNumber}`);
        console.log(`OrderDetail.jsx: Order ${orderId} status updated to RFQ Sent.`);
      } catch (err) {
        console.error("OrderDetail.jsx: Error updating order status to RFQ Sent:", err);
        setStatusUpdateMessage(`Error updating status: ${err.message}`);
      }
    } else {
      console.log(`OrderDetail.jsx: Brokerbin link clicked for ${partNumber}, but order status is not 'new' (current: ${orderData?.order?.status}). No status update performed.`);
      if (orderData?.order?.status && typeof orderData.order.status === 'string' && orderData.order.status.toLowerCase() !== 'rfq sent' && orderData.order.status.toLowerCase() !== 'processed') {
            setStatusUpdateMessage(`Order status is not 'new'. Cannot update to RFQ Sent.`);
        }
    }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    setProcessing(true);
    setProcessError(null);
    setProcessSuccess(null);
    setStatusUpdateMessage('');

    if (!selectedSupplierId) { setProcessError("Please select a supplier."); setProcessing(false); return; }
    const weightFloat = parseFloat(shipmentWeight);
    if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Please enter a valid positive shipment weight."); setProcessing(false); return; }

     let itemValidationError = null;
     const currentPurchaseItems = purchaseItemsRef.current; 
     const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
        const quantityInt = parseInt(item.quantity, 10);
        const costFloat = parseFloat(item.unit_cost);
        if (isNaN(quantityInt) || quantityInt <= 0) {
            itemValidationError = `Item #${index + 1} (SKU: ${item.sku || 'N/A'}) must have a quantity greater than 0.`; return null;
        }
        if (item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { // Allow 0 cost
            itemValidationError = `Item #${index + 1} (SKU: ${item.sku || 'N/A'}) must have a valid unit cost.`; return null;
        }
        if (!item.sku) {
             itemValidationError = `Item #${index + 1} must have a Purchase SKU.`; return null;
        }
         if (!item.description) {
             itemValidationError = `Item #${index + 1} (SKU: ${item.sku}) must have a Description.`; return null;
         }
        return {
            original_order_line_item_id: item.original_order_line_item_id,
            sku: item.sku, description: item.description, quantity: quantityInt,
            unit_cost: costFloat.toFixed(2), condition: item.condition || 'New',
        };
     }).filter(item => item !== null); // Filter out nulls from validation fails

    if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
    // const validPurchaseItems = finalPurchaseItems.filter(item => item !== null); // Already done by map then filter
    if (finalPurchaseItems.length === 0) { setProcessError("No valid line items for PO."); setProcessing(false); return; }

    const payload = {
      supplier_id: parseInt(selectedSupplierId, 10),
      payment_instructions: poNotes,
      total_shipment_weight_lbs: weightFloat,
      po_line_items: finalPurchaseItems, // Use the filtered valid items
    };
    const processApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/process`;
    console.log("OrderDetail.jsx: Submitting Process Order POST to:", processApiUrl, "Payload Preview:", JSON.stringify(payload, null, 2).substring(0, 500));


    try {
      const response = await fetch(processApiUrl, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      const responseData = await response.json().catch(() => null);
      if (!response.ok) { throw new Error(responseData?.details || responseData?.error || `HTTP error! Status: ${response.status}`); }
      setProcessSuccess(responseData.message || "Order processed successfully!");
      // Optimistically update status, or re-fetch order details
      setOrderData(prevData => ({ ...prevData, order: { ...prevData.order, status: 'Processed' } }));
    } catch (err) {
      console.error("OrderDetail.jsx: Error processing order:", err);
      setProcessError(err.message || "An unexpected error occurred.");
    } finally {
      setProcessing(false);
    }
  };

  if (loading) {
    console.log("OrderDetail.jsx: Rendering loading message");
    return <div className="loading-message">Loading order details...</div>;
  }
  if (error) {
    console.log("OrderDetail.jsx: Rendering error message:", error);
    return <div className="error-message">Error loading data: {error}</div>;
  }
  if (!orderData || !orderData.order) {
    console.log("OrderDetail.jsx: Rendering 'Order details not found.' because orderData or orderData.order is null/undefined. orderData:", orderData);
    return <p>Order details not found.</p>; 
  }

  console.log("OrderDetail.jsx: Starting main render. orderData.order is available.");

  const order = orderData.order;
  const originalLineItems = orderData.line_items || [];

  const disableProcessButton = order.status && typeof order.status === 'string' && 
                              (order.status.toLowerCase() === 'processed');
  const disableFormFields = order.status && typeof order.status === 'string' && 
                            order.status.toLowerCase() === 'processed';

  let displayOrderDate = 'N/A';
  if (order.order_date && typeof order.order_date === 'string') {
    try {
      displayOrderDate = new Date(order.order_date).toLocaleDateString();
    } catch (dateError) {
      console.error("OrderDetail.jsx: Error formatting order.order_date:", dateError);
    }
  } else if (order.order_date) {
      console.warn("OrderDetail.jsx: order.order_date is not a string:", order.order_date);
  }
  
  const displayCustomerShippingMethod = formatShippingMethod(order.customer_shipping_method);

  try {
    return (
      <div className="order-detail-container">
        <div className="order-title-section">
          <h2>
            <span style={{ color: 'white' }}>
              Order #{order.bigcommerce_order_id || 'N/A'}{' '}
            </span>
            <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order.bigcommerce_order_id)} className="copy-button" disabled={!order.bigcommerce_order_id}>📋</button>
            {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
          </h2>
          <span className={`order-status-badge status-${(order.status && typeof order.status === 'string' ? order.status.toLowerCase() : 'unknown').replace(/\s+/g, '-')}`}>
            {(order.status && typeof order.status === 'string' ? order.status : 'Unknown')}
          </span>
        </div>
        {statusUpdateMessage && <div className={processError || (statusUpdateMessage && statusUpdateMessage.toLowerCase().includes("error")) ? "error-message" : "success-message"} style={{marginTop: '10px', marginBottom: '10px'}}>{statusUpdateMessage}</div>}

        <section className="order-info card">
           <h3>Order Information</h3>
          <div><strong>Rec'd:</strong> {displayOrderDate}</div>
          <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
          <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
          <div><strong>Ship:</strong> {displayCustomerShippingMethod} to {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>
          {order.customer_notes && typeof order.customer_notes === 'string' && (
              <div style={{marginTop: '5px'}}>
                  <strong>Comments:</strong> {order.customer_notes}
              </div>
          )}
          <hr style={{margin: '10px 0'}}/>
          {originalLineItems.map((item, index) => {
              let displaySalePrice = '0.00';
              if (item.sale_price !== null && item.sale_price !== undefined) {
                  const parsedPrice = parseFloat(item.sale_price);
                  if (!isNaN(parsedPrice)) {
                      displaySalePrice = parsedPrice.toFixed(2);
                  }
              }
              return (
                  <div key={`orig-item-${item.line_item_id || index}`} className="order-info-item">
                      <span>({item.quantity || 0})</span>
                      <a
                          href={createBrokerbinLink(item.original_sku)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="link-button"
                          title={`Brokerbin: ${item.original_sku || ''}`}
                          onClick={(e) => handleBrokerbinLinkClick(e, item.original_sku)}
                      >
                        {item.original_sku || 'N/A'}
                      </a>
                      {item.hpe_option_pn && item.hpe_option_pn !== item.original_sku && (
                        <span>
                          {' ('}
                          <a
                            href={createBrokerbinLink(item.hpe_option_pn)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="link-button"
                            title={`Brokerbin: ${item.hpe_option_pn || ''}`}
                            onClick={(e) => handleBrokerbinLinkClick(e, item.hpe_option_pn)}
                          >
                            {item.hpe_option_pn}
                          </a>
                          {')'}
                        </span>
                      )}
                       <span> @ ${displaySalePrice}</span>
                  </div>
              );
          })}
        </section>
        
        <form onSubmit={handleProcessOrder} className={`processing-form ${disableFormFields ? 'form-disabled' : ''}`}>
            <section className="purchase-info card">
              <h3>Purchase Information</h3>
              <div className="form-grid">
                <label htmlFor="supplier">Supplier:</label>
                <select id="supplier" value={selectedSupplierId} onChange={handleSupplierChange} required disabled={disableFormFields || processing}><option value="">-- Select Supplier --</option>{(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name || 'Unnamed Supplier'}</option>))}</select>
                <label htmlFor="poNotes">PO Notes:</label>
                <textarea id="poNotes" value={poNotes} onChange={handlePoNotesChange} rows="3" disabled={disableFormFields || processing}/>
              </div>

              <div className="purchase-items-grid">
                <h4>Items to Purchase:</h4>
                 <div className="item-header-row">
                     <span>Purchase SKU</span>
                     <span>Description</span>
                     <span>Qty</span>
                     <span>Unit Cost</span>
                 </div>
                 {purchaseItems.map((item, index) => {
                  return (
                    <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                        <div>
                        <label className="mobile-label" htmlFor={`sku-${index}`}>Purchase SKU:</label>
                        <input id={`sku-${index}`} type="text" value={item.sku || ''} onChange={(e) => handlePurchaseItemChange(index, 'sku', e.target.value)} placeholder="Purchase SKU" required disabled={disableFormFields || processing} title={item.original_sku ? `Original: ${item.original_sku}`: ''} className="sku-input"/>
                      </div>
                       <div>
                         <label className="mobile-label" htmlFor={`desc-${index}`}>Description:</label>
                         <textarea 
                            id={`desc-${index}`} 
                            value={item.description || ''} 
                            onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} 
                            placeholder="PO Description" 
                            rows={2} 
                            disabled={disableFormFields || processing} 
                            className="description-textarea"
                          />
                       </div>
                      <div className="qty-cost-row">
                          <div>
                              <label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label>
                              <input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableFormFields || processing} className="qty-input"/>
                          </div>
                          <div>
                              <label className="mobile-label" htmlFor={`price-${index}`}>Cost:</label>
                              <input id={`price-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableFormFields || processing} className="price-input"/>
                          </div>
                      </div>
                      </div>
                  );
                })}
              </div>
            </section>

            <section className="shipment-info card">
                  <h3>Shipment Information</h3>
                   <div className="form-grid">
                      <label htmlFor="shipmentMethod">Method:</label>
                      <select id="shipmentMethod" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableFormFields || processing} required>
                          <option value="UPS Ground">UPS Ground</option>
                          <option value="UPS 2nd Day Air">UPS 2nd Day Air</option>
                          <option value="UPS Next Day Air">UPS Next Day Air</option>
                      </select>
                      <label htmlFor="shipmentWeight">Weight (lbs):</label>
                      <input type="number" id="shipmentWeight" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required disabled={disableFormFields || processing} />
                  </div>
            </section>

            <div className="action-section">
              {processSuccess && <div className="success-message" style={{ marginBottom: '10px' }}>{processSuccess}</div>}
              {processError && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}

              <button type="submit" className="process-button" disabled={processing || disableProcessButton}>
                {processing ? 'Processing...' : 'PROCESS ORDER'}
              </button>
            </div>
        </form>
      </div>
    );
  } catch (renderError) {
    console.error("OrderDetail.jsx: MAJOR RENDERING ERROR CAUGHT:", renderError);
    return <div className="error-message">A critical error occurred while rendering order details. Please check the console. Details: {String(renderError)}</div>;
  }
}

export default OrderDetail;
// --- END OF FILE OrderDetail.jsx ---