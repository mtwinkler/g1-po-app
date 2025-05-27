// src/components/DomesticOrderProcessor.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
// Import shared helpers if they are moved to a utils file, or define locally if simple
// For example: formatShippingMethod, getSelectedShippingOption, ProfitDisplay, useDebounce, escapeRegExp

const MULTI_SUPPLIER_MODE_VALUE = "_MULTI_SUPPLIER_MODE_";
const G1_ONSITE_FULFILLMENT_VALUE = "_G1_ONSITE_FULFILLMENT_";
const SHIPPING_METHODS_OPTIONS = [
    { value: "UPS Ground", label: "UPS Ground", carrier: "ups" },
    { value: "UPS 2nd Day Air", label: "UPS 2nd Day Air", carrier: "ups" },
    { value: "UPS Next Day Air", label: "UPS Next Day Air", carrier: "ups" },
    { value: "UPS Next Day Air Early A.M.", label: "UPS Next Day Air Early A.M.", carrier: "ups" },
    { value: "UPS Worldwide Expedited", label: "UPS Worldwide Expedited", carrier: "ups" },
    { value: "UPS Worldwide Express", label: "UPS Worldwide Express", carrier: "ups" },
    { value: "UPS Worldwide Saver", label: "UPS Worldwide Saver", carrier: "ups" },
    { value: "FEDEX_GROUND", label: "FedEx Ground", carrier: "fedex" },
    { value: "FEDEX_2_DAY", label: "FedEx 2Day", carrier: "fedex" },
    { value: "FEDEX_PRIORITY_OVERNIGHT", label: "FedEx Priority Overnight", carrier: "fedex" },
    { value: "FEDEX_STANDARD_OVERNIGHT", label: "FedEx Standard Overnight", carrier: "fedex" }
];

const getSelectedShippingOption = (methodValue) => {
  const foundOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === methodValue);
  return foundOption || { value: methodValue, label: methodValue || 'N/A', carrier: null };
};

const formatShippingMethod = (methodString) => {
  if (!methodString || typeof methodString !== 'string') {
    return 'N/A';
  }
  const lowerMethod = methodString.toLowerCase().trim();
  if (lowerMethod.includes('fedex')) {
    if (lowerMethod.includes('ground')) return 'FEDEX_GROUND';
    if (lowerMethod.includes('2day') || lowerMethod.includes('2 day')) return 'FEDEX_2_DAY';
    if (lowerMethod.includes('priority overnight')) return 'FEDEX_PRIORITY_OVERNIGHT';
    if (lowerMethod.includes('standard overnight')) return 'FEDEX_STANDARD_OVERNIGHT';
  }
  if (lowerMethod.includes('next day air early a.m.') || lowerMethod.includes('next day air early am') || lowerMethod.includes('next day air e')) return 'UPS Next Day Air Early A.M.';
  if (lowerMethod.includes('next day air') || lowerMethod.includes('nda')) return 'UPS Next Day Air';
  if (lowerMethod.includes('2nd day air') || lowerMethod.includes('second day air')) return 'UPS 2nd Day Air';
  if (lowerMethod.includes('ground')) return 'UPS Ground';
  if (lowerMethod.includes('worldwide expedited')) return 'UPS Worldwide Expedited';
  if (lowerMethod.includes('worldwide express')) return 'UPS Worldwide Express';
  if (lowerMethod.includes('worldwide saver')) return 'UPS Worldwide Saver';
  if (lowerMethod.includes('free shipping')) return 'UPS Ground';
  // Direct matches
  if (lowerMethod === 'ups ground') return 'UPS Ground';
  if (lowerMethod === 'ups 2nd day air') return 'UPS 2nd Day Air';
  if (lowerMethod === 'ups next day air') return 'UPS Next Day Air';
  if (lowerMethod === 'ups next day air early a.m.') return 'UPS Next Day Air Early A.M.';
  if (lowerMethod === 'ups worldwide expedited') return 'UPS Worldwide Expedited';
  if (lowerMethod === 'ups worldwide express') return 'UPS Worldwide Express';
  if (lowerMethod === 'ups worldwide saver') return 'UPS Worldwide Saver';

  const bcMatch = methodString.match(/\(([^)]+)\)/);
  if (bcMatch && bcMatch[1]) {
    const extracted = bcMatch[1].trim();
    const innerFormatted = formatShippingMethod(extracted);
    return innerFormatted !== 'N/A' ? innerFormatted : extracted;
  }
  return String(methodString).trim();
};

const ProfitDisplay = ({ info }) => {
    if (!info || !info.isCalculable) { return null; }
    const formatCurrency = (value) => {
        const numValue = Number(value);
        if (isNaN(numValue)) return 'N/A';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(numValue);
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

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => { setDebouncedValue(value); }, delay);
    return () => { clearTimeout(handler); };
  }, [value, delay]);
  return debouncedValue;
}

function escapeRegExp(string) {
  if (typeof string !== 'string') return '';
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}


function DomesticOrderProcessor({ 
    orderData, 
    suppliers, 
    apiService, 
    fetchOrderAndSuppliers, 
    setProcessSuccess, 
    setProcessSuccessMessage, 
    setProcessedPOsInfo, 
    setProcessError: setGlobalProcessError 
}) {
  const navigate = useNavigate();
  const { order, line_items: originalLineItemsFromData } = orderData;
  const orderId = order.id;

  const [processing, setProcessing] = useState(false);
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [shipmentMethod, setShipmentMethod] = useState('UPS Ground');
  const [shipmentWeight, setShipmentWeight] = useState('');
  const [selectedMainSupplierTrigger, setSelectedMainSupplierTrigger] = useState('');
  const [isMultiSupplierMode, setIsMultiSupplierMode] = useState(false);
  const [isG1OnsiteFulfillmentMode, setIsG1OnsiteFulfillmentMode] = useState(false);
  const [singleOrderPoNotes, setSingleOrderPoNotes] = useState('');
  const [lineItemAssignments, setLineItemAssignments] = useState({});
  const [poNotesBySupplier, setPoNotesBySupplier] = useState({});
  const [multiSupplierItemCosts, setMultiSupplierItemCosts] = useState({});
  const [multiSupplierItemDescriptions, setMultiSupplierItemDescriptions] = useState({});
  const [multiSupplierShipmentDetails, setMultiSupplierShipmentDetails] = useState({});
  const [originalCustomerShippingMethod, setOriginalCustomerShippingMethod] = useState('UPS Ground');
  const [billToCustomerFedex, setBillToCustomerFedex] = useState(false);
  const [customerFedexAccountNumber, setCustomerFedexAccountNumber] = useState('');
  const [billToCustomerUps, setBillToCustomerUps] = useState(false);
  const [customerUpsAccountNumber, setCustomerUpsAccountNumber] = useState('');
  const [isBlindDropShip, setIsBlindDropShip] = useState(false);
  const [localProcessError, setLocalProcessError] = useState(null); 

  const [profitInfo, setProfitInfo] = useState({
      totalRevenue: 0,
      totalCost: 0,
      profitAmount: 0,
      profitMargin: 0,
      isCalculable: false
  });

  const cleanPullSuffix = " - clean pull";
  const originalLineItems = originalLineItemsFromData || [];
  const currentSelectedShippingOption = getSelectedShippingOption(shipmentMethod);

  useEffect(() => {
    if (isMultiSupplierMode && originalLineItems.length <= 1) {
      setIsMultiSupplierMode(false);
      if (selectedMainSupplierTrigger === MULTI_SUPPLIER_MODE_VALUE) {
        setSelectedMainSupplierTrigger('');
      }
    }
  }, [originalLineItems.length, isMultiSupplierMode, selectedMainSupplierTrigger]);

  // Initialize form states when orderData is available
  useEffect(() => {
    if (order) {
        let determinedInitialShipMethod = 'UPS Ground';
        if (order.is_bill_to_customer_account && order.customer_selected_freight_service) {
            const customerSelectedService = formatShippingMethod(order.customer_selected_freight_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'ups');
            if (matchedOption) {
                determinedInitialShipMethod = matchedOption.value;
                setBillToCustomerUps(true);
                setCustomerUpsAccountNumber(order.customer_ups_account_number || '');
            }
        } else if (order.is_bill_to_customer_fedex_account && order.customer_selected_fedex_service) {
            const customerSelectedService = formatShippingMethod(order.customer_selected_fedex_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
            if (matchedOption) {
                determinedInitialShipMethod = matchedOption.value;
                setBillToCustomerFedex(true);
                setCustomerFedexAccountNumber(order.customer_fedex_account_number || '');
            }
        } else if (order.customer_shipping_method) { 
            const parsedOrderMethod = formatShippingMethod(order.customer_shipping_method);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
            if (matchedOption) {
                determinedInitialShipMethod = matchedOption.value;
                if (matchedOption.carrier === 'ups' && order.is_bill_to_customer_account) {
                   setBillToCustomerUps(true);
                   setCustomerUpsAccountNumber(order.customer_ups_account_number || '');
                } else if (matchedOption.carrier === 'fedex' && order.is_bill_to_customer_fedex_account) {
                   setBillToCustomerFedex(true);
                   setCustomerFedexAccountNumber(order.customer_fedex_account_number || '');
                }
            }
        }
        setShipmentMethod(determinedInitialShipMethod);
        setOriginalCustomerShippingMethod(determinedInitialShipMethod);
    }
    if (originalLineItems) {
        const initialItemsForPoForm = originalLineItems.map(item => ({
            original_order_line_item_id: item.line_item_id,
            sku: item.hpe_option_pn || item.original_sku || '',
            description: (item.hpe_po_description || item.line_item_name || '') + ( (item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
            skuInputValue: item.hpe_option_pn || item.original_sku || '',
            quantity: item.quantity || 1, unit_cost: '', condition: 'New',
            original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn,
            original_name: item.line_item_name, hpe_po_description: item.hpe_po_description,
            hpe_pn_type: item.hpe_pn_type,
        }));
        setPurchaseItems(initialItemsForPoForm);
        const initialMultiDesc = {};
        originalLineItems.forEach(item => {
            let defaultDescription = item.hpe_po_description || item.line_item_name || '';
            if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) defaultDescription += cleanPullSuffix;
            else if (!defaultDescription && item.original_sku) defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
            initialMultiDesc[item.line_item_id] = defaultDescription;
        });
        setMultiSupplierItemDescriptions(initialMultiDesc);
    } else {
        setPurchaseItems([]);
        setMultiSupplierItemDescriptions({});
    }
     // Reset other states on order change
    setSelectedMainSupplierTrigger('');
    setIsMultiSupplierMode(false);
    setIsG1OnsiteFulfillmentMode(false);
    setSingleOrderPoNotes('');
    setLineItemAssignments({});
    setPoNotesBySupplier({});
    setMultiSupplierItemCosts({});
    // setMultiSupplierItemDescriptions({}); // Already handled above
    setMultiSupplierShipmentDetails({});
    setShipmentWeight('');
    setIsBlindDropShip(false);

  }, [orderData, cleanPullSuffix]); // Depends on orderData to initialize

  // Profit Calculation useEffect (Moved from OrderDetail)
  useEffect(() => {
    if (!orderData || !order || !originalLineItems) {
        if (profitInfo.isCalculable) { 
            setProfitInfo(prev => ({ ...prev, isCalculable: false, totalRevenue: 0, totalCost: 0, profitAmount: 0, profitMargin: 0 }));
        }
        return;
    }

    let calculatedItemsRevenue = 0;
    if (originalLineItems && originalLineItems.length > 0) {
        calculatedItemsRevenue = originalLineItems.reduce((sum, item) => {
            const price = parseFloat(item.sale_price || 0);
            const quantity = parseInt(item.quantity || 0, 10);
            return sum + (price * quantity);
        }, 0);
    }
    const revenue = calculatedItemsRevenue;
    let cost = 0;
    let isCalculable = false; // Default to false
    
    // For pending orders, calculate cost based on current form inputs
    if (isG1OnsiteFulfillmentMode) {
        cost = 0; // G1 Onsite has no PO cost input here
        isCalculable = revenue > 0 || originalLineItems.length === 0; // Calculable if there's revenue or no items
    } else if (isMultiSupplierMode) {
        const assignedItems = originalLineItems.filter(item => lineItemAssignments[item.line_item_id]);
        if (assignedItems.length > 0 && assignedItems.length === originalLineItems.length) { // All items must be assigned
            const allCostsEntered = assignedItems.every(item => {
                const itemCost = multiSupplierItemCosts[item.line_item_id];
                return itemCost !== undefined && itemCost !== '' && !isNaN(parseFloat(itemCost));
            });
            if (allCostsEntered) {
                cost = assignedItems.reduce((total, item) => {
                    const itemCostNum = parseFloat(multiSupplierItemCosts[item.line_item_id]);
                    const quantityNum = parseInt(item.quantity, 10);
                    return total + (itemCostNum * quantityNum);
                }, 0);
                isCalculable = true;
            }
        }
    } else if (selectedMainSupplierTrigger && selectedMainSupplierTrigger !== MULTI_SUPPLIER_MODE_VALUE && selectedMainSupplierTrigger !== G1_ONSITE_FULFILLMENT_VALUE) { // Single Supplier
        if (purchaseItems.length > 0) {
            const allCostsEntered = purchaseItems.every(item => {
                return item.unit_cost !== undefined && item.unit_cost !== '' && !isNaN(parseFloat(item.unit_cost));
            });
            if (allCostsEntered) {
                cost = purchaseItems.reduce((total, item) => {
                    const itemCostNum = parseFloat(item.unit_cost);
                    const quantityNum = parseInt(item.quantity, 10);
                    return total + (itemCostNum * quantityNum);
                }, 0);
                isCalculable = true;
            }
        } else if (originalLineItems.length === 0) { // No items to purchase
             isCalculable = true; 
             cost = 0;
        }
    }
    
    // Override if order status is already processed (handled by OrderDetail, but good to be defensive)
    // This component primarily calculates for PENDING orders. Processed order profit is shown by OrderDetail.
    if (order.status?.toLowerCase() === 'processed') {
       isCalculable = false; // Let OrderDetail handle processed profit display
    }


    if (revenue === 0 && originalLineItems.length === 0 && order.status?.toLowerCase() !== 'processed') {
       isCalculable = false; // Cannot calculate if no revenue and no items, unless processed
    }


    setProfitInfo(currentProfitInfo => {
        if (isCalculable) {
            const profit = revenue - cost;
            const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
            if (currentProfitInfo.totalRevenue !== revenue || currentProfitInfo.totalCost !== cost || currentProfitInfo.profitAmount !== profit || currentProfitInfo.profitMargin !== margin || !currentProfitInfo.isCalculable) {
                return { totalRevenue: revenue, totalCost: cost, profitAmount: profit, profitMargin: margin, isCalculable: true };
            }
        } else {
            if (currentProfitInfo.isCalculable) { // Only update if it was previously calculable
                return { totalRevenue: revenue, totalCost: 0, profitAmount: 0, profitMargin: 0, isCalculable: false };
            }
        }
        return currentProfitInfo;
    });

  }, [orderData, order, originalLineItems, purchaseItems, multiSupplierItemCosts, isMultiSupplierMode, isG1OnsiteFulfillmentMode, selectedMainSupplierTrigger, lineItemAssignments, profitInfo.isCalculable]);


  // SKU description lookup
  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);
  useEffect(() => {
    if (!apiService || !debouncedSku || skuToLookup.index === -1 || isMultiSupplierMode || isG1OnsiteFulfillmentMode) return;
    const abortController = new AbortController();
    const fetchDescription = async () => {
      try {
        const data = await apiService.get(`/lookup/description/${encodeURIComponent(String(debouncedSku).trim())}`);
        if (abortController.signal.aborted) return;
        setPurchaseItems(prevItems => {
            const updatedItems = [...prevItems];
            if (updatedItems[skuToLookup.index]?.skuInputValue === debouncedSku) {
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) {
                    newDescription += cleanPullSuffix;
                } else if (!newDescription) {
                    const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDesc ? existingDesc + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) newDescription = cleanPullSuffix.trim();
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
            }
            return updatedItems;
        });
      } catch (error) { 
          if (error.name !== 'AbortError' && error.status !== 401 && error.status !== 403) {
            console.error("Error fetching description:", error);
          }
      }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, apiService, isMultiSupplierMode, isG1OnsiteFulfillmentMode]);

  // --- Handlers (Copied and adapted from OrderDetail.jsx) ---
  const handleMainSupplierTriggerChange = (e) => {
    const value = e.target.value;
    setSelectedMainSupplierTrigger(value);
    setLocalProcessError(null); setGlobalProcessError(null); 
    setProcessSuccess(false);

    let defaultMethodForThisMode = 'UPS Ground';
    if (order) {
        if (order.is_bill_to_customer_account && order.customer_selected_freight_service) {
            const customerSelectedService = formatShippingMethod(order.customer_selected_freight_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'ups');
            if (matchedOption) defaultMethodForThisMode = matchedOption.value;
        } else if (order.is_bill_to_customer_fedex_account && order.customer_selected_fedex_service) {
            const customerSelectedService = formatShippingMethod(order.customer_selected_fedex_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
            if (matchedOption) defaultMethodForThisMode = matchedOption.value;
        } else if (order.customer_shipping_method) {
            const parsedOrderMethod = formatShippingMethod(order.customer_shipping_method);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
            if (matchedOption) defaultMethodForThisMode = matchedOption.value;
        }
    }
    setOriginalCustomerShippingMethod(defaultMethodForThisMode);
    setShipmentMethod(defaultMethodForThisMode);
    setShipmentWeight('');
    setIsBlindDropShip(false);

    const newSelectedOption = getSelectedShippingOption(defaultMethodForThisMode);
    if (newSelectedOption.carrier === 'ups' && order?.is_bill_to_customer_account) {
        setBillToCustomerUps(true); setCustomerUpsAccountNumber(order.customer_ups_account_number || '');
        setBillToCustomerFedex(false); setCustomerFedexAccountNumber('');
    } else if (newSelectedOption.carrier === 'fedex' && order?.is_bill_to_customer_fedex_account) {
        setBillToCustomerFedex(true); setCustomerFedexAccountNumber(order.customer_fedex_account_number || '');
        setBillToCustomerUps(false); setCustomerUpsAccountNumber('');
    } else {
        setBillToCustomerFedex(false); setCustomerFedexAccountNumber('');
        setBillToCustomerUps(false); setCustomerUpsAccountNumber('');
    }

    if (value === G1_ONSITE_FULFILLMENT_VALUE) {
        setIsG1OnsiteFulfillmentMode(true); setIsMultiSupplierMode(false); setSingleOrderPoNotes(''); setPurchaseItems([]);
        setLineItemAssignments({}); setPoNotesBySupplier({}); setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({}); setMultiSupplierShipmentDetails({});
    } else if (value === MULTI_SUPPLIER_MODE_VALUE) {
        setIsG1OnsiteFulfillmentMode(false); setIsMultiSupplierMode(true); setSingleOrderPoNotes(''); setPurchaseItems([]);
        const initialMultiDesc = {};
        if (originalLineItems) {
            originalLineItems.forEach(item => {
                let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) defaultDescription += cleanPullSuffix;
                else if (!defaultDescription && item.original_sku) defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
                initialMultiDesc[item.line_item_id] = defaultDescription;
            });
        }
        setMultiSupplierItemDescriptions(initialMultiDesc);
        setLineItemAssignments({}); setPoNotesBySupplier({}); setMultiSupplierItemCosts({});
        const newMultiShipDetails = {};
        // Initialize shipment details for already assigned items if any (though lineItemAssignments is cleared above)
        // This part might need adjustment based on when assignments happen vs. mode switch
        setMultiSupplierShipmentDetails(newMultiShipDetails);
    } else { 
        setIsG1OnsiteFulfillmentMode(false); setIsMultiSupplierMode(false);
        const s = suppliers.find(sup => sup.id === parseInt(value, 10));
        setSingleOrderPoNotes(s?.defaultponotes || '');
        if (originalLineItems) {
            const initialItemsForPoForm = originalLineItems.map(item => ({
                original_order_line_item_id: item.line_item_id, sku: item.hpe_option_pn || item.original_sku || '',
                description: (item.hpe_po_description || item.line_item_name || '') + ( (item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
                skuInputValue: item.hpe_option_pn || item.original_sku || '', quantity: item.quantity || 1, unit_cost: '', condition: 'New',
                original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn, original_name: item.line_item_name,
                hpe_po_description: item.hpe_po_description, hpe_pn_type: item.hpe_pn_type,
            }));
            setPurchaseItems(initialItemsForPoForm);
        } else { setPurchaseItems([]); }
        setLineItemAssignments({}); setPoNotesBySupplier({}); setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({}); setMultiSupplierShipmentDetails({});
    }
  };
  const handleSingleOrderPoNotesChange = (e) => setSingleOrderPoNotes(e.target.value);
  const handleLineItemSupplierAssignment = (originalLineItemId, supplierId) => {
    setLineItemAssignments(prev => ({ ...prev, [originalLineItemId]: supplierId }));
    if (supplierId && !poNotesBySupplier[supplierId]) {
        const s = suppliers.find(sup => sup.id === parseInt(supplierId, 10));
        setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: s?.defaultponotes || '' }));
    }
    if (supplierId && isMultiSupplierMode && !multiSupplierShipmentDetails[supplierId]) {
        const initialShipOptionForMulti = getSelectedShippingOption(originalCustomerShippingMethod);
        setMultiSupplierShipmentDetails(prev => ({
            ...prev,
            [supplierId]: {
                method: originalCustomerShippingMethod, weight: '',
                billToCustomerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && order?.is_bill_to_customer_account,
                customerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && order?.is_bill_to_customer_account ? (order.customer_ups_account_number || '') : '',
                billToCustomerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && order?.is_bill_to_customer_fedex_account,
                customerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && order?.is_bill_to_customer_fedex_account ? (order.customer_fedex_account_number || '') : ''
            }
        }));
    }
  };
  const handlePoNotesBySupplierChange = (supplierId, notes) => setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: notes }));
  const handleMultiSupplierItemCostChange = (originalLineItemId, cost) => setMultiSupplierItemCosts(prev => ({ ...prev, [originalLineItemId]: cost }));
  const handleMultiSupplierItemDescriptionChange = (originalLineItemId, description) => setMultiSupplierItemDescriptions(prev => ({ ...prev, [originalLineItemId]: description }));
  const handleMultiSupplierShipmentDetailChange = (supplierId, field, value) => {
    setMultiSupplierShipmentDetails(prev => {
        const currentDetails = prev[supplierId] || { method: originalCustomerShippingMethod, weight: '' };
        const newDetailsForSupplier = { ...currentDetails, [field]: value };
        if (field === 'method') {
            const selectedOpt = getSelectedShippingOption(value);
            if (selectedOpt?.carrier === 'ups') {
                newDetailsForSupplier.billToCustomerUpsAccount = order?.is_bill_to_customer_account || false;
                newDetailsForSupplier.customerUpsAccount = (order?.is_bill_to_customer_account && order?.customer_ups_account_number) ? order.customer_ups_account_number : '';
                newDetailsForSupplier.billToCustomerFedexAccount = false; newDetailsForSupplier.customerFedexAccount = '';
            } else if (selectedOpt?.carrier === 'fedex') {
                newDetailsForSupplier.billToCustomerFedexAccount = order?.is_bill_to_customer_fedex_account || false;
                newDetailsForSupplier.customerFedexAccount = (order?.is_bill_to_customer_fedex_account && order?.customer_fedex_account_number) ? order.customer_fedex_account_number : '';
                newDetailsForSupplier.billToCustomerUpsAccount = false; newDetailsForSupplier.customerUpsAccount = '';
            } else { 
                newDetailsForSupplier.billToCustomerUpsAccount = false; newDetailsForSupplier.customerUpsAccount = '';
                newDetailsForSupplier.billToCustomerFedexAccount = false; newDetailsForSupplier.customerFedexAccount = '';
            }
        }
        return { ...prev, [supplierId]: newDetailsForSupplier };
    });
  };
  const handlePurchaseItemChange = (index, field, value) => {
    setPurchaseItems(prevItems => {
        const items = [...prevItems];
        if (items[index]) {
            items[index] = { ...items[index], [field]: value };
            if (field === 'skuInputValue') {
                const trimmedSku = String(value).trim();
                items[index].skuInputValue = trimmedSku; items[index].sku = trimmedSku;
                setSkuToLookup({ index, sku: trimmedSku });
            }
        }
        return items;
    });
  };
  const handleShipmentMethodChange = (e) => {
    const newMethod = e.target.value;
    setShipmentMethod(newMethod);
    const selectedOpt = getSelectedShippingOption(newMethod);
    if (selectedOpt?.carrier === 'ups') {
        setBillToCustomerUps(order?.is_bill_to_customer_account || false);
        setCustomerUpsAccountNumber((order?.is_bill_to_customer_account && order?.customer_ups_account_number) ? order.customer_ups_account_number : '');
        setBillToCustomerFedex(false); setCustomerFedexAccountNumber('');
    } else if (selectedOpt?.carrier === 'fedex') {
        setBillToCustomerFedex(order?.is_bill_to_customer_fedex_account || false);
        setCustomerFedexAccountNumber((order?.is_bill_to_customer_fedex_account && order?.customer_fedex_account_number) ? order.customer_fedex_account_number : '');
        setBillToCustomerUps(false); setCustomerUpsAccountNumber('');
    } else {
        setBillToCustomerFedex(false); setCustomerFedexAccountNumber('');
        setBillToCustomerUps(false); setCustomerUpsAccountNumber('');
    }
  };
  const handleShipmentWeightChange = (e) => setShipmentWeight(e.target.value);
  const handleBrandingChange = (event) => setIsBlindDropShip(event.target.value === 'blind');

  // handleProcessOrder - This is a very large function. It needs to be copied from the original OrderDetail.jsx
  // and adapted to use the local state and props of this DomesticOrderProcessor component.
  const handleProcessOrder = async (e) => {
    e.preventDefault();
    if (!apiService) { 
        setGlobalProcessError("API service is not available."); 
        return; 
    }
    setProcessing(true); 
    setLocalProcessError(null); 
    setGlobalProcessError(null); // Clear global error from parent
    setProcessSuccess(false); // Use parent's setter

    let payloadAssignments = [];
    // --- Copy the ENTIRE logic for building payloadAssignments from the original OrderDetail.jsx's handleProcessOrder ---
    // Make sure to use local state variables like:
    // isG1OnsiteFulfillmentMode, isMultiSupplierMode, selectedMainSupplierTrigger,
    // purchaseItems, lineItemAssignments, multiSupplierItemCosts, multiSupplierItemDescriptions,
    // multiSupplierShipmentDetails, shipmentMethod, shipmentWeight,
    // billToCustomerFedex, customerFedexAccountNumber, billToCustomerUps, customerUpsAccountNumber, isBlindDropShip
    // currentSelectedShippingOption (derived from local shipmentMethod or multi-supplier details)
    // originalLineItems (from props: orderData.line_items)
    // suppliers (from props)
    // order (from props: orderData.order)
    // cleanPullSuffix
    // G1_ONSITE_FULFILLMENT_VALUE, MULTI_SUPPLIER_MODE_VALUE
    // Make sure to use `setLocalProcessError` for errors specific to this form validation.

    // --- START OF COPIED/ADAPTED LOGIC from original handleProcessOrder for payloadAssignments ---
    if (isG1OnsiteFulfillmentMode) {
        if (originalLineItems.length > 0) {
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setLocalProcessError("Invalid shipment weight for G1 Onsite Fulfillment."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShippingOption) { setLocalProcessError("Please select a shipment method for G1 Onsite Fulfillment."); setProcessing(false); return; }
            if (currentSelectedShippingOption.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setLocalProcessError("Customer FedEx Account Number is required for G1 Onsite Bill Recipient (FedEx)."); setProcessing(false); return;
            }
            if (currentSelectedShippingOption.carrier === 'ups' && billToCustomerUps && !customerUpsAccountNumber.trim()) {
                setLocalProcessError("Customer UPS Account Number is required for G1 Onsite Bill Recipient (UPS)."); setProcessing(false); return;
            }
        }
        payloadAssignments.push({
            supplier_id: G1_ONSITE_FULFILLMENT_VALUE,
            payment_instructions: "G1 Onsite Fulfillment",
            po_line_items: [], // G1 onsite uses original line items, not PO items for cost
            total_shipment_weight_lbs: originalLineItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null,
            shipment_method: originalLineItems.length > 0 ? shipmentMethod : null,
            carrier: originalLineItems.length > 0 ? (currentSelectedShippingOption?.carrier || null) : null,
            is_bill_to_customer_fedex_account: originalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' ? billToCustomerFedex : false,
            customer_fedex_account_number: originalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
            is_bill_to_customer_ups_account: originalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' ? billToCustomerUps : false,
            customer_ups_account_number: originalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' && billToCustomerUps ? customerUpsAccountNumber.trim() : null,
            is_blind_drop_ship: isBlindDropShip
        });
    } else if (isMultiSupplierMode) {
        const assignedSupplierIds = [...new Set(Object.values(lineItemAssignments))].filter(id => id);
        if (originalLineItems.length > 0) {
             if (assignedSupplierIds.length === 0) { setLocalProcessError("Multi-Supplier Mode: Assign items to at least one supplier."); setProcessing(false); return; }
             if (!originalLineItems.every(item => !!lineItemAssignments[item.line_item_id])) { setLocalProcessError("Multi-Supplier Mode: Assign all original items to a supplier."); setProcessing(false); return; }
        }

        for (const supId of assignedSupplierIds) {
            const supplier = suppliers.find(s => s.id === parseInt(supId, 10));
            const itemsForThisSupplier = originalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supId);
            if (itemsForThisSupplier.length > 0) {
                let itemCostValidationError = null;
                const poLineItems = itemsForThisSupplier.map(item => {
                    const costStr = multiSupplierItemCosts[item.line_item_id]; const costFloat = parseFloat(costStr);
                    if (costStr === undefined || costStr === '' || isNaN(costFloat) || costFloat < 0) { itemCostValidationError = `Missing/invalid unit cost for SKU ${item.original_sku || 'N/A'} (Supplier: ${supplier?.name}).`; return null; }
                    let descriptionForPo = multiSupplierItemDescriptions[item.line_item_id];
                    if (descriptionForPo === undefined) descriptionForPo = item.hpe_po_description || item.line_item_name || `${item.original_sku || ''}${cleanPullSuffix}`;
                    if (!String(descriptionForPo).trim()) { itemCostValidationError = `Missing description for SKU ${item.original_sku || 'N/A'} (Supplier: ${supplier?.name}).`; return null; }
                    return { original_order_line_item_id: item.line_item_id, sku: item.hpe_option_pn || item.original_sku, description: String(descriptionForPo).trim(), quantity: item.quantity, unit_cost: costFloat.toFixed(2), condition: 'New' };
                }).filter(Boolean);

                if (itemCostValidationError) { setLocalProcessError(itemCostValidationError); setProcessing(false); return; }
                if (poLineItems.length !== itemsForThisSupplier.length && itemsForThisSupplier.length > 0) { setLocalProcessError("One or more items for a supplier had validation errors."); setProcessing(false); return; }

                const shipmentDetailsForThisPo = multiSupplierShipmentDetails[supId] || {};
                const currentPoMethod = shipmentDetailsForThisPo.method;
                const currentPoWeight = shipmentDetailsForThisPo.weight;
                const currentSelectedShipOptionMulti = getSelectedShippingOption(currentPoMethod);

                if (currentPoMethod && (!currentPoWeight || parseFloat(currentPoWeight) <= 0)) { setLocalProcessError(`Invalid/missing weight for PO to ${supplier?.name}.`); setProcessing(false); return; }
                if (!currentPoMethod && currentPoWeight && parseFloat(currentPoWeight) > 0) { setLocalProcessError(`Shipping method required for PO to ${supplier?.name}.`); setProcessing(false); return; }
                
                const isFedexBillRecipientMulti = shipmentDetailsForThisPo.billToCustomerFedexAccount || false;
                const fedexAccountNumMulti = shipmentDetailsForThisPo.customerFedexAccount || '';
                const isUpsBillRecipientMulti = shipmentDetailsForThisPo.billToCustomerUpsAccount || false;
                const upsAccountNumMulti = shipmentDetailsForThisPo.customerUpsAccount || '';

                if (currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti && !fedexAccountNumMulti.trim()) {
                    setLocalProcessError(`Customer FedEx Account Number is required for PO to ${supplier?.name}.`); setProcessing(false); return;
                }
                if (currentSelectedShipOptionMulti?.carrier === 'ups' && isUpsBillRecipientMulti && !upsAccountNumMulti.trim()) {
                    setLocalProcessError(`Customer UPS Account Number is required for PO to ${supplier?.name}.`); setProcessing(false); return;
                }

                payloadAssignments.push({
                    supplier_id: parseInt(supId, 10),
                    payment_instructions: poNotesBySupplier[supId] || "",
                    po_line_items: poLineItems,
                    total_shipment_weight_lbs: currentPoWeight ? parseFloat(currentPoWeight).toFixed(1) : null,
                    shipment_method: currentPoMethod || null,
                    carrier: currentSelectedShipOptionMulti?.carrier || (currentPoMethod ? null : null),
                    is_bill_to_customer_fedex_account: currentSelectedShipOptionMulti?.carrier === 'fedex' ? isFedexBillRecipientMulti : false,
                    customer_fedex_account_number: currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti ? fedexAccountNumMulti.trim() : null,
                    is_bill_to_customer_ups_account: currentSelectedShipOptionMulti?.carrier === 'ups' ? isUpsBillRecipientMulti : false,
                    customer_ups_account_number: currentSelectedShipOptionMulti?.carrier === 'ups' && isUpsBillRecipientMulti ? upsAccountNumMulti.trim() : null,
                    is_blind_drop_ship: isBlindDropShip 
                });
            }
        }
        if (payloadAssignments.length === 0 && originalLineItems.length > 0) { setLocalProcessError("No items assigned for PO generation in multi-supplier mode."); setProcessing(false); return; }

    } else { // Single Supplier Mode
        const singleSelectedSupId = selectedMainSupplierTrigger;
        if (!singleSelectedSupId || singleSelectedSupId === MULTI_SUPPLIER_MODE_VALUE || singleSelectedSupId === G1_ONSITE_FULFILLMENT_VALUE) {
            setLocalProcessError("Please select a supplier."); setProcessing(false); return;
        }
        const currentPurchaseItems = purchaseItems; 

        if (currentPurchaseItems.length > 0) { // Only require weight/method if there are items
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setLocalProcessError("Invalid shipment weight."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShippingOption) { setLocalProcessError("Please select a shipment method."); setProcessing(false); return; }
             if (currentSelectedShippingOption.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setLocalProcessError("Customer FedEx Account Number is required for Bill Recipient (FedEx)."); setProcessing(false); return;
            }
            if (currentSelectedShippingOption.carrier === 'ups' && billToCustomerUps && !customerUpsAccountNumber.trim()) {
                setLocalProcessError("Customer UPS Account Number is required for Bill Recipient (UPS)."); setProcessing(false); return;
            }
        }

        let itemValidationError = null;
        const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10); const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1}: Quantity must be greater than 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1}: Unit cost is invalid or missing.`; return null; }
            if (!String(item.skuInputValue).trim()) { itemValidationError = `Item #${index + 1}: SKU is required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `Item #${index + 1}: Description is required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.skuInputValue).trim(), description: String(item.description).trim(), quantity: quantityInt, unit_cost: costFloat.toFixed(2), condition: item.condition || 'New' };
        }).filter(Boolean);

        if (itemValidationError) { setLocalProcessError(itemValidationError); setProcessing(false); return; }
        // Allow processing even if finalPurchaseItems is empty IF originalLineItems was also empty (e.g. service order)
        if (finalPurchaseItems.length === 0 && originalLineItems.length > 0) { setLocalProcessError("No valid line items to purchase for the PO."); setProcessing(false); return; }
        
        // Ensure payload is added if there are items OR if it's a service order (no items but supplier selected)
        if (finalPurchaseItems.length > 0 || originalLineItems.length === 0) { 
            payloadAssignments.push({
                supplier_id: parseInt(singleSelectedSupId, 10),
                payment_instructions: singleOrderPoNotes,
                total_shipment_weight_lbs: finalPurchaseItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null, // Weight only if items
                shipment_method: finalPurchaseItems.length > 0 ? shipmentMethod : null, // Method only if items
                po_line_items: finalPurchaseItems,
                carrier: finalPurchaseItems.length > 0 ? (currentSelectedShippingOption?.carrier || null) : null,
                is_bill_to_customer_fedex_account: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' ? billToCustomerFedex : false,
                customer_fedex_account_number: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
                is_bill_to_customer_ups_account: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' ? billToCustomerUps : false,
                customer_ups_account_number: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' && billToCustomerUps ? customerUpsAccountNumber.trim() : null,
                is_blind_drop_ship: isBlindDropShip
            });
        }
    }

    if (payloadAssignments.length === 0 && originalLineItems.length > 0 && !isG1OnsiteFulfillmentMode) { 
        setLocalProcessError("No data prepared for PO generation. Please check item assignments or supplier details."); 
        setProcessing(false); return; 
    }
    if (payloadAssignments.length === 0 && originalLineItems.length === 0 && selectedMainSupplierTrigger === "" && !isG1OnsiteFulfillmentMode ) { 
        setLocalProcessError("Please select a supplier or fulfillment mode."); 
        setProcessing(false); return; 
    }
    // --- END OF COPIED/ADAPTED LOGIC ---

    try {
        const finalPayload = { assignments: payloadAssignments };
        const responseData = await apiService.post(`/orders/${order.id}/process`, finalPayload);
        setProcessSuccess(true);
        setProcessSuccessMessage(responseData.message || "Order processed successfully!");
        if(setProcessedPOsInfo) setProcessedPOsInfo(Array.isArray(responseData.processed_purchase_orders) ? responseData.processed_purchase_orders : []);
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, true); 
    } catch (err) {
        let errorMsg = err.data?.error || err.data?.message || err.message || "Unexpected error during processing.";
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setLocalProcessError(errorMsg);
        setGlobalProcessError(errorMsg);
        setProcessSuccess(false); 
        if(setProcessedPOsInfo) setProcessedPOsInfo([]);
    } finally { setProcessing(false); }
  };


  const disableAllActions = processing; // Simpler disable flag
  const disableEditableFormFields = order?.status?.toLowerCase() === 'processed' || order?.status?.toLowerCase() === 'completed offline' || processing;


  // JSX for DomesticOrderProcessor - This will be the forms from original OrderDetail
  return (
    <>
      <section className="supplier-mode-selection card">
        <h3>Order Fulfillment</h3>
        <div className="form-grid">
            <label htmlFor="mainSupplierTrigger" style={{ marginRight: '8px' }}>Initiate Fulfillment Strategy:</label>
            <select
                id="mainSupplierTrigger"
                value={selectedMainSupplierTrigger}
                onChange={handleMainSupplierTriggerChange}
                disabled={disableAllActions || (suppliers.length === 0 && originalLineItems.length === 0) }
                style={{ flexGrow: 1 }}
            >
                <option value="">-- Select Supplier --</option>
                {(suppliers || []).map(supplier => (
                    <option key={supplier.id} value={supplier.id}>
                        {supplier.name || 'Unnamed Supplier'}
                    </option>
                ))}
                {originalLineItems.length > 1 && (
                    <option value={MULTI_SUPPLIER_MODE_VALUE}>** Use Multiple Suppliers **</option>
                )}
                {originalLineItems.length > 0 && (
                   <option value={G1_ONSITE_FULFILLMENT_VALUE}>G1 Onsite Fulfillment</option>
                )}
            </select>
        </div>
      </section>

      {/* Form for Single Regular Supplier PO - Copied and adapted from original OrderDetail.jsx */}
      {!isMultiSupplierMode && !isG1OnsiteFulfillmentMode && selectedMainSupplierTrigger &&
       selectedMainSupplierTrigger !== MULTI_SUPPLIER_MODE_VALUE && selectedMainSupplierTrigger !== G1_ONSITE_FULFILLMENT_VALUE && (
        <form onSubmit={handleProcessOrder} className={`processing-form ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="purchase-info card">
              <h3>Create PO for {suppliers.find(s=>s.id === parseInt(selectedMainSupplierTrigger, 10))?.name || ''}</h3>
              <div className="form-grid">
                <label htmlFor="singlePoNotes">PO Notes:</label>
                <textarea id="singlePoNotes" value={singleOrderPoNotes} onChange={handleSingleOrderPoNotesChange} rows="3" disabled={disableEditableFormFields} />
              </div>
              <div className="purchase-items-grid">
                <h4>Items to Purchase:</h4>
                <div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                {purchaseItems.map((item, index) => (
                     <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                        <div>
                            <label className="mobile-label" htmlFor={`sku-${index}`}>SKU:</label>
                            <input id={`sku-${index}`} type="text" value={item.skuInputValue || ''} onChange={(e) => handlePurchaseItemChange(index, 'skuInputValue', e.target.value)} placeholder="SKU" required disabled={disableEditableFormFields} title={item.original_sku ? `Original: ${item.original_sku}` : ''} className="sku-input" />
                        </div>
                        <div>
                            <label className="mobile-label" htmlFor={`desc-${index}`}>Desc:</label>
                            <textarea id={`desc-${index}`} value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableEditableFormFields} className="description-textarea" />
                        </div>
                        <div className="qty-cost-row">
                            <div>
                                <label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label>
                                <input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableEditableFormFields} className="qty-input" />
                            </div>
                            <div>
                                <label className="mobile-label" htmlFor={`cost-${index}`}>Cost:</label>
                                <input id={`cost-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableEditableFormFields} className="price-input" />
                            </div>
                        </div>
                    </div>
                ))}
              </div>
            </section>

            <ProfitDisplay info={profitInfo} />

            <section className="shipment-info card">
              <h3>Shipment Information</h3>
              <div className="form-grid">
                <label htmlFor="shipmentMethodSingle">Method:</label>
                <select
                  id="shipmentMethodSingle"
                  value={shipmentMethod}
                  onChange={handleShipmentMethodChange}
                  disabled={disableEditableFormFields}
                  required={(originalLineItems || []).length > 0 && purchaseItems.length > 0}
                >
                    {SHIPPING_METHODS_OPTIONS.map((opt, index) => <option key={`${opt.value}-${opt.carrier}-single-${index}`} value={opt.value}>{opt.label}</option>)}
                </select>

                <label htmlFor="shipmentWeightSingle">Weight (lbs):</label>
                <input
                    type="number"
                    id="shipmentWeightSingle"
                    className="weight-input-field"
                    value={shipmentWeight}
                    onChange={handleShipmentWeightChange}
                    step="0.1" min="0.1"
                    placeholder="e.g., 5.0"
                    required={(originalLineItems || []).length > 0 && purchaseItems.length > 0}
                    disabled={disableEditableFormFields}
                />

                {currentSelectedShippingOption?.carrier === 'fedex' && (
                <>
                    <label htmlFor="billToCustomerFedexSingle">Bill Customer FedEx:</label>
                    <input type="checkbox" id="billToCustomerFedexSingle" checked={billToCustomerFedex}
                        onChange={(e) => {
                            setBillToCustomerFedex(e.target.checked);
                            if (e.target.checked && order?.is_bill_to_customer_fedex_account && order?.customer_fedex_account_number) {
                                setCustomerFedexAccountNumber(order.customer_fedex_account_number);
                            } else if (!e.target.checked) {setCustomerFedexAccountNumber('');}
                        }} disabled={disableEditableFormFields} />
                    {billToCustomerFedex && (
                    <><label htmlFor="customerFedexAccountSingle">Customer FedEx Acct #:</label>
                        <input type="text" id="customerFedexAccountSingle" value={customerFedexAccountNumber} onChange={(e) => setCustomerFedexAccountNumber(e.target.value)} placeholder="FedEx Account Number" required disabled={disableEditableFormFields} />
                    </>)}
                </>)}
               {currentSelectedShippingOption?.carrier === 'ups' && (
                <>
                    <label htmlFor="billToCustomerUpsSingle">Bill Customer UPS:</label>
                    <input type="checkbox" id="billToCustomerUpsSingle" checked={billToCustomerUps}
                        onChange={(e) => {
                            setBillToCustomerUps(e.target.checked);
                            if (e.target.checked && order?.is_bill_to_customer_account && order?.customer_ups_account_number) {
                                setCustomerUpsAccountNumber(order.customer_ups_account_number);
                            } else if (!e.target.checked) {setCustomerUpsAccountNumber('');}
                        }} disabled={disableEditableFormFields} />
                    {billToCustomerUps && (
                    <><label htmlFor="customerUpsAccountSingle">Customer UPS Acct #:</label>
                        <input type="text" id="customerUpsAccountSingle" value={customerUpsAccountNumber} onChange={(e) => setCustomerUpsAccountNumber(e.target.value)} placeholder="UPS Account Number" required disabled={disableEditableFormFields} />
                    </>)}
                </>)}
              </div>
            </section>

            <section className="branding-options-section card" style={{ marginTop: 'var(--spacing-lg)' }}>
                <h3>Branding Options</h3>
                <div className="form-grid"> 
                    <label htmlFor="brandingOptionSingle">Branding:</label>
                    <select id="brandingOptionSingle" value={isBlindDropShip ? 'blind' : 'g1'} onChange={handleBrandingChange} disabled={disableEditableFormFields}>
                        <option value="g1">Global One Technology Branding</option>
                        <option value="blind">Blind Ship (Generic Packing Slip)</option>
                    </select>
                </div>
            </section>   
             <div className="order-actions"> <button type="submit" disabled={disableAllActions || processing} className="process-order-button"> {processing ? 'Processing Single PO...' : 'PROCESS SINGLE SUPPLIER PO'} </button> </div>
        </form>
      )}

      {/* Form for Multi-Supplier Mode - Copied and adapted from original OrderDetail.jsx */}
      {isMultiSupplierMode && !isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form multi-supplier-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="multi-supplier-assignment card">
                <h3>Assign Original Items to Suppliers</h3>
                {originalLineItems.length === 0 && <p>No original line items to assign.</p>}
                {originalLineItems.map((item) => (
                    <div key={`assign-item-${item.line_item_id}`} className="item-assignment-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-sm)'}}>
                        <span style={{ flexBasis: '60%' }}>({item.quantity}) {item.original_sku || 'N/A'}</span>
                        <select value={lineItemAssignments[item.line_item_id] || ''} onChange={(e) => handleLineItemSupplierAssignment(item.line_item_id, e.target.value)} disabled={disableAllActions || suppliers.length === 0} style={{flexBasis: '35%'}}>
                            <option value="">-- Assign Supplier --</option>
                            {(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name}</option>))}
                        </select>
                    </div>
                ))}
            </section>
            {[...new Set(Object.values(lineItemAssignments))].filter(id => id).map(supplierId => {
                const supplier = suppliers.find(s => s.id === parseInt(supplierId, 10));
                if (!supplier) return null;
                const itemsForThisSupplier = originalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supplierId);
                const currentPoShipDetails = multiSupplierShipmentDetails[supplierId] || {};
                const selectedPoShipOption = getSelectedShippingOption(currentPoShipDetails.method);
                return (
                    <section key={supplierId} className="supplier-po-draft card">
                        <h4>PO Draft for: {supplier.name}</h4>
                        <div className="purchase-items-grid multi-supplier-items">
                            {itemsForThisSupplier.map(item => (
                                <div key={`multi-item-${item.line_item_id}`} className="item-row-multi">
                                    <div className="item-info-multi"> Qty {item.quantity} of {item.original_sku || 'N/A'} </div>
                                    <div className="item-description-multi">
                                        <label className="mobile-label" htmlFor={`desc-multi-${item.line_item_id}`}>Description:</label>
                                        <textarea id={`desc-multi-${item.line_item_id}`} value={multiSupplierItemDescriptions[item.line_item_id] || ''} onChange={(e) => handleMultiSupplierItemDescriptionChange(item.line_item_id, e.target.value)} placeholder="Item Description for PO" rows={2} disabled={disableAllActions} className="description-textarea-multi" />
                                    </div>
                                    <div className="item-cost-multi">
                                      <label htmlFor={`cost-multi-${item.line_item_id}`} className="mobile-label">Unit Cost:</label>
                                      <input id={`cost-multi-${item.line_item_id}`} type="number" value={multiSupplierItemCosts[item.line_item_id] || ''} onChange={(e) => handleMultiSupplierItemCostChange(item.line_item_id, e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableAllActions} className="price-input" />
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="form-grid shipment-details-multi card-inset" style={{border: '1px solid var(--border-medium)', padding: 'var(--spacing-md)', borderRadius: '4px', marginTop: 'var(--spacing-md)'}}>
                           {/* ... Multi-supplier shipment details form structure ... */}
                        </div>
                        <div className="form-grid" style={{marginTop: 'var(--spacing-md)'}}>
                            <label htmlFor={`poNotes-${supplierId}`} style={{gridColumn: '1 / -1', textAlign: 'left'}}>PO Notes for {supplier.name}:</label>
                            <textarea id={`poNotes-${supplierId}`} value={poNotesBySupplier[supplierId] || ''} onChange={(e) => handlePoNotesBySupplierChange(supplierId, e.target.value)} rows="3" disabled={disableAllActions} style={{gridColumn: '1 / -1', width: '100%'}}/>
                        </div>
                    </section>
                );
            })}
            <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
                 <h3>Packing Slip Branding</h3>
                 <div className="form-grid">
                    <label htmlFor="brandingOptionMultiGlobal">Branding:</label>
                    <select id="brandingOptionMultiGlobal" value={isBlindDropShip ? 'blind' : 'g1'} onChange={handleBrandingChange} disabled={disableEditableFormFields}>
                        <option value="g1">Global One Technology Branding</option>
                        <option value="blind">Blind Ship (Generic Packing Slip)</option>
                    </select>
                </div>
            </section>
            <ProfitDisplay info={profitInfo} />
            <div className="order-actions"> <button type="submit" disabled={disableAllActions || processing || [...new Set(Object.values(lineItemAssignments))].filter(id => id).length === 0} className="process-order-button"> {processing ? 'Processing Multiple POs...' : 'PROCESS ALL ASSIGNED POs'} </button> </div>
        </form>
      )}

      {/* Form for G1 Onsite Fulfillment - Copied and adapted from original OrderDetail.jsx */}
      {isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form g1-onsite-fulfillment-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
          <section className="shipment-info card">
            <h3>Shipment Information</h3>
            <div className="form-grid">
              <label htmlFor="shipmentMethodG1">Method:</label>
              <select id="shipmentMethodG1" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableEditableFormFields} required={originalLineItems.length > 0}>
                  {SHIPPING_METHODS_OPTIONS.map((opt, index) => <option key={`${opt.value}-${opt.carrier}-g1-${index}`} value={opt.value}>{opt.label}</option>)}
              </select>
              <label htmlFor="shipmentWeightG1">Weight (lbs):</label>
              <input type="number" id="shipmentWeightG1" className="weight-input-field" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required={originalLineItems.length > 0} disabled={disableEditableFormFields} />
              <label htmlFor="brandingOptionG1">Branding:</label>
              <select id="brandingOptionG1" value={isBlindDropShip ? 'blind' : 'g1'} onChange={handleBrandingChange} disabled={disableEditableFormFields}>
                  <option value="g1">Global One Technology Branding</option>
                  <option value="blind">Blind Ship (Generic Packing Slip)</option>
              </select>
              {currentSelectedShippingOption?.carrier === 'fedex' && originalLineItems.length > 0 && (
                <>{/* ... FedEx bill to customer options ... */}</>
               )}
               {currentSelectedShippingOption?.carrier === 'ups' && originalLineItems.length > 0 && (
                <>{/* ... UPS bill to customer options ... */}</>
               )}
            </div>
            </section>
            {/* ProfitDisplay is intentionally NOT shown for PENDING G1 Onsite as cost is 0 */}
            <div className="order-actions"> <button type="submit" disabled={disableAllActions || processing} className="process-order-button"> {processing ? 'Processing G1 Fulfillment...' : 'PROCESS G1 ONSITE FULFILLMENT'} </button> </div>
        </form>
      )}
      {localProcessError && <div className="error-message" style={{ marginTop: '10px' }}>{localProcessError}</div>}
    </>
  );
}

export default DomesticOrderProcessor;