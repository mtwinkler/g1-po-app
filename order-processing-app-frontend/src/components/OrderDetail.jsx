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

const createBrokerbinLink = (partNumber) => {
  if (!partNumber) return '#';
  const trimmedPartNumber = String(partNumber).trim();
  if (!trimmedPartNumber) return '#';
  const encodedPartNumber = encodeURIComponent(trimmedPartNumber);
  return `https://members.brokerbin.com/partkey?login=g1tech&parts=${encodedPartNumber}`;
};

function escapeRegExp(string) {
  if (typeof string !== 'string') return '';
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

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

function OrderDetail() {
  const { orderId } = useParams();
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const navigate = useNavigate();

  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(false);
  const [processSuccessMessage, setProcessSuccessMessage] = useState('');
  const [processedPOsInfo, setProcessedPOsInfo] = useState([]);
  const [processError, setProcessError] = useState(null);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');
  const [manualStatusUpdateInProgress, setManualStatusUpdateInProgress] = useState(false);
  const [seeQuotesStatus, setSeeQuotesStatus] = useState('');

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
  
  const [isBlindDropShip, setIsBlindDropShip] = useState(false);

  const [lineItemSpares, setLineItemSpares] = useState({});
  const [loadingSpares, setLoadingSpares] = useState(false);

  const cleanPullSuffix = " - clean pull";
  const originalLineItems = orderData?.line_items || [];

  const getSelectedShippingOption = (methodValue) => {
    return SHIPPING_METHODS_OPTIONS.find(opt => opt.value === methodValue);
  };

  const handleSeeQuotesClick = async () => {
    if (!orderData?.order?.bigcommerce_order_id) {
      setSeeQuotesStatus('Error: Order number not available.');
      setTimeout(() => setSeeQuotesStatus(''), 3000);
      return;
    }
    const orderNumber = orderData.order.bigcommerce_order_id;
    const searchPhrase = `Show me, in list format, the quoted prices received only today for Brokerbin RFQ and order number ${orderNumber}. Also include any comments included with the quotes. Disregard anything below "From: Global One Technology Group" in the emails. Note that "ea" is an abbreviation for each.`;
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

  useEffect(() => {
    const currentLineItemsCount = originalLineItems.length;
    if (isMultiSupplierMode && currentLineItemsCount <= 1) {
      setIsMultiSupplierMode(false);
      if (selectedMainSupplierTrigger === MULTI_SUPPLIER_MODE_VALUE) {
        setSelectedMainSupplierTrigger('');
      }
    }
  }, [originalLineItems.length, isMultiSupplierMode, selectedMainSupplierTrigger]);

  const fetchOrderAndSuppliers = useCallback(async (signal, isPostProcessRefresh = false) => {
    if (!currentUser) {
        setLoading(false); setOrderData(null); setSuppliers([]); return;
    }
    setLoading(true); setError(null);

    if (!isPostProcessRefresh) {
        setProcessSuccess(false); setProcessSuccessMessage('');
        setProcessedPOsInfo([]); setProcessError(null);
        setIsBlindDropShip(false); 
    }
    setStatusUpdateMessage('');

    try {
        const [fetchedOrderData, fetchedSuppliers] = await Promise.all([
            apiService.get(`/orders/${orderId}`),
            apiService.get(`/suppliers`)
        ]);
        if (signal?.aborted) return;

        setOrderData(fetchedOrderData);
        setSuppliers(fetchedSuppliers || []);

        if (!isPostProcessRefresh) {
            setLineItemSpares({});
            setMultiSupplierItemCosts({});
            setMultiSupplierShipmentDetails({});
            setLineItemAssignments({});
            setPoNotesBySupplier({});
            setBillToCustomerFedex(false); 
            setCustomerFedexAccountNumber('');

            if (fetchedOrderData?.order) {
                const orderDetails = fetchedOrderData.order;
                let determinedInitialShipMethod = 'UPS Ground'; 
                let determinedInitialCarrier = 'ups';

                if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) { 
                    const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
                    const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService);
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        determinedInitialCarrier = matchedOption.carrier;
                    }
                } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) { 
                    const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
                     const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        determinedInitialCarrier = 'fedex';
                        setBillToCustomerFedex(true);
                        setCustomerFedexAccountNumber(orderDetails.customer_fedex_account_number || '');
                    }
                } else if (orderDetails.customer_shipping_method) { 
                    const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
                    const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        determinedInitialCarrier = matchedOption.carrier;
                         if (matchedOption.carrier === 'fedex' && orderDetails.is_bill_to_customer_fedex_account) {
                            setBillToCustomerFedex(true);
                            setCustomerFedexAccountNumber(orderDetails.customer_fedex_account_number || '');
                        }
                    }
                }
                setShipmentMethod(determinedInitialShipMethod);
                setOriginalCustomerShippingMethod(determinedInitialShipMethod); 

                const initialSelectedShippingOption = getSelectedShippingOption(determinedInitialShipMethod);
                if (initialSelectedShippingOption?.carrier === 'fedex') {
                    if (orderDetails.is_bill_to_customer_fedex_account) {
                        setBillToCustomerFedex(true);
                        setCustomerFedexAccountNumber(orderDetails.customer_fedex_account_number || '');
                    } else {
                        setBillToCustomerFedex(false);
                        setCustomerFedexAccountNumber('');
                    }
                } else { 
                    setBillToCustomerFedex(false);
                    setCustomerFedexAccountNumber('');
                }
            }


            if (fetchedOrderData?.line_items) {
                const initialItemsForPoForm = fetchedOrderData.line_items.map(item => ({
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
                fetchedOrderData.line_items.forEach(item => {
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
        } else if (fetchedOrderData?.order) { 
            const orderDetails = fetchedOrderData.order;
            let determinedOriginalMethod = 'UPS Ground';
             if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) { 
                const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === customerSelectedService)) determinedOriginalMethod = customerSelectedService;
            } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) { 
                const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === customerSelectedService && opt.carrier === 'fedex')) determinedOriginalMethod = customerSelectedService;
            } else if (orderDetails.customer_shipping_method) {
                const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === parsedOrderMethod)) determinedOriginalMethod = parsedOrderMethod;
            }
            setOriginalCustomerShippingMethod(determinedOriginalMethod); 
        }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error in fetchOrderAndSuppliers:", err);
        setError(err.data?.message || err.message || "An unknown error occurred fetching data.");
      }
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, cleanPullSuffix, currentUser, apiService]);

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

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  useEffect(() => {
    if (!currentUser || !debouncedSku || skuToLookup.index === -1 || isMultiSupplierMode || isG1OnsiteFulfillmentMode || !apiService) return;
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
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) {
                        newDescription = cleanPullSuffix.trim();
                    }
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
            }
            return updatedItems;
        });
      } catch (error) {
        if (error.name !== 'AbortError' && error.status !== 401 && error.status !== 403) {
            console.error("Error fetching description:", error);
        } else if (error.status === 401 || error.status === 403) {
            console.error("Unauthorized to fetch SKU description.");
        }
      }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, currentUser, isMultiSupplierMode, isG1OnsiteFulfillmentMode, apiService]);

  const handleMainSupplierTriggerChange = (e) => {
    const value = e.target.value;
    setSelectedMainSupplierTrigger(value);
    setProcessError(null); setProcessSuccess(false);
    setProcessSuccessMessage(''); setProcessedPOsInfo([]);

    let defaultMethodForThisMode = 'UPS Ground'; 
    let defaultCarrier = 'ups';

    if (orderData?.order) {
        const orderDetails = orderData.order;
        if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) { 
            const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService);
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
                defaultCarrier = matchedOption.carrier;
            }
        } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) { 
            const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
                defaultCarrier = 'fedex';
            }
        } else if (orderDetails.customer_shipping_method) {
            const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
                defaultCarrier = matchedOption.carrier;
            }
        }
    }
    setOriginalCustomerShippingMethod(defaultMethodForThisMode); 
    setShipmentMethod(defaultMethodForThisMode); 
    setShipmentWeight('');

    if (defaultCarrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account) {
        setBillToCustomerFedex(true);
        setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number || '');
    } else {
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
    }


    if (value === G1_ONSITE_FULFILLMENT_VALUE) {
        setIsG1OnsiteFulfillmentMode(true); setIsMultiSupplierMode(false);
        setSingleOrderPoNotes('');
        setPurchaseItems([]);
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({});
        setMultiSupplierShipmentDetails({});
    } else if (value === MULTI_SUPPLIER_MODE_VALUE) {
        setIsG1OnsiteFulfillmentMode(false); setIsMultiSupplierMode(true);
        setSingleOrderPoNotes('');
        setPurchaseItems([]);
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
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({});
        const newMultiShipDetails = {};
        Object.keys(lineItemAssignments).forEach(itemId => { 
            const supId = lineItemAssignments[itemId];
            if (supId && !newMultiShipDetails[supId]) {
                newMultiShipDetails[supId] = { method: defaultMethodForThisMode, weight: '' };
            }
        });
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
        } else {
            setPurchaseItems([]);
        }
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({});
        setMultiSupplierShipmentDetails({});
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
        setMultiSupplierShipmentDetails(prev => ({
            ...prev,
            [supplierId]: { method: originalCustomerShippingMethod, weight: '' } 
        }));
    }
  };

  const handlePoNotesBySupplierChange = (supplierId, notes) => {
    setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: notes }));
  };

  const handleMultiSupplierItemCostChange = (originalLineItemId, cost) => {
    setMultiSupplierItemCosts(prev => ({ ...prev, [originalLineItemId]: cost }));
  };

  const handleMultiSupplierItemDescriptionChange = (originalLineItemId, description) => {
    setMultiSupplierItemDescriptions(prev => ({ ...prev, [originalLineItemId]: description }));
  };

  const handleMultiSupplierShipmentDetailChange = (supplierId, field, value) => {
    setMultiSupplierShipmentDetails(prev => {
        const newDetails = {
            ...prev,
            [supplierId]: {
                ...(prev[supplierId] || { method: originalCustomerShippingMethod, weight: '' }),
                [field]: value
            }
        };
        if (field === 'method') {
            const selectedOpt = getSelectedShippingOption(value);
            if (selectedOpt?.carrier !== 'fedex') {
                newDetails[supplierId].billToCustomerFedexAccount = false;
                newDetails[supplierId].customerFedexAccount = '';
            } else if (selectedOpt?.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account) {
                newDetails[supplierId].billToCustomerFedexAccount = true;
                newDetails[supplierId].customerFedexAccount = orderData.order.customer_fedex_account_number || '';
            }
        }
        return newDetails;
    });
  };

  const handlePurchaseItemChange = (index, field, value) => {
    setPurchaseItems(prevItems => {
        const items = [...prevItems];
        if (items[index]) {
            items[index] = { ...items[index], [field]: value };
            if (field === 'skuInputValue') {
                const trimmedSku = String(value).trim();
                items[index].skuInputValue = trimmedSku;
                items[index].sku = trimmedSku;
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
    if (selectedOpt?.carrier !== 'fedex') {
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
    } else if (selectedOpt?.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account) {
        setBillToCustomerFedex(true);
        setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number || '');
    }
  };
  const handleShipmentWeightChange = (e) => setShipmentWeight(e.target.value);

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

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    if (!currentUser || !apiService) { setProcessError("Please log in or API service unavailable."); return; }
    setProcessing(true); setProcessError(null); setProcessSuccess(false);
    setProcessSuccessMessage(''); setProcessedPOsInfo([]); setStatusUpdateMessage('');

    let payloadAssignments = [];

    if (isG1OnsiteFulfillmentMode) {
        const currentSelectedShipOption = getSelectedShippingOption(shipmentMethod);
        if (originalLineItems.length > 0) { 
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight for G1 Onsite Fulfillment."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShipOption) { setProcessError("Please select a shipment method for G1 Onsite Fulfillment."); setProcessing(false); return; }
             if (currentSelectedShipOption.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setProcessError("Customer FedEx Account Number is required for G1 Onsite Bill Recipient."); setProcessing(false); return;
            }
        }
        payloadAssignments.push({
            supplier_id: G1_ONSITE_FULFILLMENT_VALUE,
            payment_instructions: "G1 Onsite Fulfillment",
            po_line_items: [], 
            total_shipment_weight_lbs: originalLineItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null,
            shipment_method: originalLineItems.length > 0 ? shipmentMethod : null,
            carrier: originalLineItems.length > 0 ? (currentSelectedShipOption?.carrier || 'ups') : null,
            is_bill_to_customer_fedex_account: originalLineItems.length > 0 && currentSelectedShipOption?.carrier === 'fedex' ? billToCustomerFedex : false,
            customer_fedex_account_number: originalLineItems.length > 0 && currentSelectedShipOption?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
            is_blind_drop_ship: isBlindDropShip 
        });
    } else if (isMultiSupplierMode) {
        const assignedSupplierIds = [...new Set(Object.values(lineItemAssignments))].filter(id => id);
        if (originalLineItems.length > 0) {
             if (assignedSupplierIds.length === 0) { setProcessError("Multi-Supplier Mode: Assign items to at least one supplier."); setProcessing(false); return; }
             if (!originalLineItems.every(item => !!lineItemAssignments[item.line_item_id])) { setProcessError("Multi-Supplier Mode: Assign all original items to a supplier."); setProcessing(false); return; }
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

                if (itemCostValidationError) { setProcessError(itemCostValidationError); setProcessing(false); return; }
                if (poLineItems.length !== itemsForThisSupplier.length && itemsForThisSupplier.length > 0) { setProcessError("One or more items for a supplier had validation errors."); setProcessing(false); return; }

                const shipmentDetailsForThisPo = multiSupplierShipmentDetails[supId] || {};
                const currentPoMethod = shipmentDetailsForThisPo.method;
                const currentPoWeight = shipmentDetailsForThisPo.weight;
                const currentSelectedShipOptionMulti = getSelectedShippingOption(currentPoMethod);

                if (currentPoMethod && (!currentPoWeight || parseFloat(currentPoWeight) <= 0)) { setProcessError(`Invalid/missing weight for PO to ${supplier?.name}.`); setProcessing(false); return; }
                if (!currentPoMethod && currentPoWeight && parseFloat(currentPoWeight) > 0) { setProcessError(`Shipping method required for PO to ${supplier?.name}.`); setProcessing(false); return; }

                const isFedexBillRecipientMulti = shipmentDetailsForThisPo.billToCustomerFedexAccount || false; 
                const fedexAccountNumMulti = shipmentDetailsForThisPo.customerFedexAccount || '';  

                if (currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti && !fedexAccountNumMulti.trim()) {
                    setProcessError(`Customer FedEx Account Number is required for PO to ${supplier?.name} when 'Bill to Customer' is checked.`); setProcessing(false); return;
                }

                payloadAssignments.push({
                    supplier_id: parseInt(supId, 10),
                    payment_instructions: poNotesBySupplier[supId] || "",
                    po_line_items: poLineItems,
                    total_shipment_weight_lbs: currentPoWeight ? parseFloat(currentPoWeight).toFixed(1) : null,
                    shipment_method: currentPoMethod || null,
                    carrier: currentSelectedShipOptionMulti?.carrier || (currentPoMethod ? 'ups' : null),
                    is_bill_to_customer_fedex_account: currentSelectedShipOptionMulti?.carrier === 'fedex' ? isFedexBillRecipientMulti : false,
                    customer_fedex_account_number: currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti ? fedexAccountNumMulti.trim() : null,
                    is_blind_drop_ship: isBlindDropShip 
                });
            }
        }
        if (payloadAssignments.length === 0 && originalLineItems.length > 0) { setProcessError("No items assigned for PO generation in multi-supplier mode."); setProcessing(false); return; }

    } else { // Single Supplier Mode
        const singleSelectedSupId = selectedMainSupplierTrigger;
        if (!singleSelectedSupId || singleSelectedSupId === MULTI_SUPPLIER_MODE_VALUE || singleSelectedSupId === G1_ONSITE_FULFILLMENT_VALUE) {
            setProcessError("Please select a supplier."); setProcessing(false); return;
        }
        const currentPurchaseItems = purchaseItems;
        const currentSelectedShipOptionSingle = getSelectedShippingOption(shipmentMethod);

        if (currentPurchaseItems.length > 0) { 
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShipOptionSingle) { setProcessError("Please select a shipment method."); setProcessing(false); return; }
            if (currentSelectedShipOptionSingle.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setProcessError("Customer FedEx Account Number is required when 'Bill to Customer' is checked."); setProcessing(false); return;
            }
        }

        let itemValidationError = null;
        const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10); const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1}: Quantity > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1}: Unit cost invalid.`; return null; }
            if (!String(item.skuInputValue).trim()) { itemValidationError = `Item #${index + 1}: SKU required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `Item #${index + 1}: Description required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.skuInputValue).trim(), description: String(item.description).trim(), quantity: quantityInt, unit_cost: costFloat.toFixed(2), condition: item.condition || 'New' };
        }).filter(Boolean);

        if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
        if (finalPurchaseItems.length === 0 && originalLineItems.length > 0) { setProcessError("No valid line items for PO."); setProcessing(false); return; }

        if (finalPurchaseItems.length > 0 || originalLineItems.length === 0) { 
            payloadAssignments.push({
                supplier_id: parseInt(singleSelectedSupId, 10),
                payment_instructions: singleOrderPoNotes,
                total_shipment_weight_lbs: finalPurchaseItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null,
                shipment_method: finalPurchaseItems.length > 0 ? shipmentMethod : null,
                po_line_items: finalPurchaseItems,
                carrier: finalPurchaseItems.length > 0 ? (currentSelectedShipOptionSingle?.carrier || 'ups') : null,
                is_bill_to_customer_fedex_account: finalPurchaseItems.length > 0 && currentSelectedShipOptionSingle?.carrier === 'fedex' ? billToCustomerFedex : false,
                customer_fedex_account_number: finalPurchaseItems.length > 0 && currentSelectedShipOptionSingle?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
                is_blind_drop_ship: isBlindDropShip 
            });
        }
    }

    if (payloadAssignments.length === 0 && originalLineItems.length > 0 && !isG1OnsiteFulfillmentMode) { setProcessError("No data for POs. Check assignments/details."); setProcessing(false); return; }
    if (payloadAssignments.length === 0 && originalLineItems.length === 0 && selectedMainSupplierTrigger === "") { setProcessError("Select supplier/mode."); setProcessing(false); return; }


    try {
        const finalPayload = { assignments: payloadAssignments };
        const responseData = await apiService.post(`/orders/${orderId}/process`, finalPayload);
        setProcessSuccess(true);
        setProcessSuccessMessage(responseData.message || "Order processed successfully!");
        setProcessedPOsInfo(Array.isArray(responseData.processed_purchase_orders) ? responseData.processed_purchase_orders : []);
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, true);
    } catch (err) {
        let errorMsg = err.data?.error || err.data?.message || err.message || "Unexpected error during processing.";
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setProcessError(errorMsg);
        setProcessSuccess(false); setProcessedPOsInfo([]);
    } finally { setProcessing(false); }
  };

  if (authLoading) return <div className="loading-message">Loading session...</div>;
  if (!currentUser && !authLoading) return <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}><h2>Order Details</h2><p className="error-message">Please <Link to="/login">log in</Link>.</p></div>;
  if (loading && !orderData && !processSuccess) return <div className="loading-message">Loading order details...</div>;
  if (error && !loading) return <div className="error-message" style={{ margin: '20px', padding: '20px', border: '1px solid red' }}>Error: {error}</div>;

  const order = orderData?.order;

  if (!order && !processSuccess && !loading) {
      return <p style={{ textAlign: 'center', marginTop: '20px' }}>Order details not found or error loading.</p>;
  }

  const isActuallyProcessed = order?.status?.toLowerCase() === 'processed' || order?.status?.toLowerCase() === 'completed offline';
  const canDisplayProcessingForm = !processSuccess && !isActuallyProcessed;
  const disableAllActions = processing || manualStatusUpdateInProgress;
  const disableEditableFormFields = isActuallyProcessed || disableAllActions || processSuccess;

  let displayOrderDate = 'N/A';
  if (order?.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) { /* ignore */ }

  let displayShipMethodInOrderInfo = 'N/A';
  if (order) {
    if (order.is_bill_to_customer_account && order.customer_selected_freight_service) { 
        displayShipMethodInOrderInfo = formatShippingMethod(order.customer_selected_freight_service);
    } else if (order.is_bill_to_customer_fedex_account && order.customer_selected_fedex_service) { 
        displayShipMethodInOrderInfo = formatShippingMethod(order.customer_selected_fedex_service);
    } else if (order.customer_shipping_method) {
        displayShipMethodInOrderInfo = formatShippingMethod(order.customer_shipping_method);
    }
  }

  const currentSelectedShippingOption = getSelectedShippingOption(shipmentMethod);

  return (
    <div className="order-detail-container">
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

      {statusUpdateMessage && !processError && !processSuccess && (
          <div className={statusUpdateMessage.toLowerCase().includes("error") ? "error-message" : "success-message"} style={{ marginTop: '10px', marginBottom: '10px' }}>
              {statusUpdateMessage}
          </div>
      )}

      {processError && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}

      {processSuccess && (
        <div className="process-success-container card">
          <p className="success-message-large">ORDER PROCESSED SUCCESSFULLY!</p>
          
          <div className="dashboard-link-container" style={{ marginTop: 'var(--spacing-md)', marginBottom: 'var(--spacing-lg)', textAlign: 'center' }}>
            <a
              href="https://store-g6oxherh18.mybigcommerce.com/manage/orders"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-info" 
            >
              G1 BC Order Dashboard
            </a>
          </div>

          {processSuccessMessage && (
            <p className="success-message-detail" style={{textAlign: 'center', marginBottom: 'var(--spacing-lg)'}}>{processSuccessMessage}</p>
          )}
            {processedPOsInfo.length > 0 && (
                <div className="processed-pos-info">
                    <h4>Generated Documents:</h4>
                    <ul>
                        {processedPOsInfo.map((poInfo, index) => (
                            <li key={index}>
                                <strong>PO #: {poInfo.po_number}</strong> (Supplier ID: {poInfo.supplier_id})
                                {poInfo.is_blind_drop_ship && <span style={{color: 'var(--primary-accent)', fontStyle: 'italic'}}> (Blind Drop Ship)</span>}
                                {poInfo.tracking_number && <span> - Tracking: {poInfo.tracking_number}</span>}
                                <div className="doc-links">
                                    {poInfo.po_pdf_gcs_uri && <a href={poInfo.po_pdf_gcs_uri} target="_blank" rel="noopener noreferrer" className="link-button">PO PDF</a>}
                                    {poInfo.packing_slip_gcs_uri && <a href={poInfo.packing_slip_gcs_uri} target="_blank" rel="noopener noreferrer" className="link-button">Packing Slip</a>}
                                    {poInfo.label_gcs_uri && <a href={poInfo.label_gcs_uri} target="_blank" rel="noopener noreferrer" className="link-button">Shipping Label</a>}
                                </div>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
      )}

      {orderData?.order?.status?.toLowerCase() === 'rfq sent' && orderData?.order?.bigcommerce_order_id && !isActuallyProcessed && !processSuccess && (
        <section className="see-quotes-gmail-card card">
         <div className="button-container-center">
            <button
              onClick={handleSeeQuotesClick}
              className="btn btn-primary"
              disabled={processing || manualStatusUpdateInProgress}
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
        <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
        <div><strong>Ship:</strong> {displayShipMethodInOrderInfo} to {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>

        {order.is_bill_to_customer_account && order.customer_ups_account_number && (
          <div className="customer-account-info">
            <strong>Bill Shipping To:</strong> Customer UPS Account # {order.customer_ups_account_number}
            {order.customer_selected_freight_service && ` (Service: ${formatShippingMethod(order.customer_selected_freight_service)})`}
          </div>
        )}
        {order.is_bill_to_customer_fedex_account && order.customer_fedex_account_number && (
            <div className="customer-account-info">
                <strong>Bill Shipping To:</strong> Customer FedEx Account # {order.customer_fedex_account_number}
                {order.customer_selected_fedex_service && ` (Service: ${formatShippingMethod(order.customer_selected_fedex_service)})`}
            </div>
        )}

        {order.customer_notes && (<div style={{ marginTop: '5px' }}><strong>Comments:</strong> {order.customer_notes}</div>)}
        <hr style={{ margin: '10px 0' }} />
        {originalLineItems.map((item) => (
            <p key={`orig-item-${item.line_item_id}`} className="order-info-sku-line">
                <span>({item.quantity || 0}) </span>
                <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.original_sku}`} onClick={(e) => handlePartNumberLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>
                {loadingSpares && item.hpe_pn_type === 'option' && !lineItemSpares[item.line_item_id] && <span className="loading-text"> (loading spare...)</span>}
                {lineItemSpares[item.line_item_id] && ( <span style={{ fontStyle: 'italic', marginLeft: '5px' }}>( <a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handlePartNumberLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a> )</span> )}
                {item.hpe_option_pn && String(item.hpe_option_pn).trim() !== String(item.original_sku).trim() && String(item.hpe_option_pn).trim() !== lineItemSpares[item.line_item_id] && ( <span>{' ('} <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handlePartNumberLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a> {')'}</span> )}
                <span> @ ${parseFloat(item.sale_price || 0).toFixed(2)}</span>
            </p>
        ))}
      </section>
      )}

     {canDisplayProcessingForm && (
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
     )}

      {/* Form for Single Regular Supplier PO */}
      {canDisplayProcessingForm && !isMultiSupplierMode && !isG1OnsiteFulfillmentMode && selectedMainSupplierTrigger &&
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
            <section className="shipment-info card">
              <h3>Shipment Information</h3>
              <div className="form-grid">
                <label htmlFor="shipmentMethodSingle">Method:</label>
                <select 
                  id="shipmentMethodSingle" 
                  value={shipmentMethod} 
                  onChange={handleShipmentMethodChange} 
                  disabled={disableEditableFormFields} 
                  required={originalLineItems.length > 0 && !isG1OnsiteFulfillmentMode && purchaseItems.length > 0}
                >
                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={`${opt.value}-${opt.carrier}`} value={opt.value}>{opt.label}</option>)}
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
                    required={originalLineItems.length > 0 && !isG1OnsiteFulfillmentMode && purchaseItems.length > 0}
                    disabled={disableEditableFormFields} 
                />
                
                {/* "Blind Ship?" Label occupies the first column of a new grid row */}
                <label htmlFor="isBlindDropShipSingle" className="blind-ship-grid-label-col1">Blind Ship?</label>
                {/* Empty cell for the grid's second column on this label's row */}
                <div className="form-grid-empty-cell"></div> 

                {/* Checkbox wrapper occupies the first column of the next grid row, visually under its label */}
                <div className="blind-ship-checkbox-wrapper-col1"> 
                    <input
                        type="checkbox"
                        id="isBlindDropShipSingle" // ID is linked from the label above
                        className="blind-ship-checkbox-input"
                        checked={isBlindDropShip}
                        onChange={(e) => setIsBlindDropShip(e.target.checked)}
                        disabled={disableEditableFormFields}
                    />
                </div>
                {/* Empty cell for the grid's second column on this checkbox's row */}
                <div className="form-grid-empty-cell"></div>

              </div>
              {currentSelectedShippingOption?.carrier === 'fedex' && (
                <>
                    <div className="form-grid" style={{marginTop: '10px'}}>
                        <label htmlFor="billToCustomerFedexSingle">Bill to Customer's FedEx Account:</label>
                        <input
                        type="checkbox"
                        id="billToCustomerFedexSingle"
                        checked={billToCustomerFedex}
                        onChange={(e) => {
                            setBillToCustomerFedex(e.target.checked);
                            if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number);
                            } else if (!e.target.checked) {
                                setCustomerFedexAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                        style={{ justifySelf: 'start' }} 
                        />
                    </div>
                    {billToCustomerFedex && (
                        <div className="form-grid" style={{marginTop: '5px'}}>
                        <label htmlFor="customerFedexAccountSingle">Customer FedEx Account #:</label>
                        <input
                            type="text"
                            id="customerFedexAccountSingle"
                            value={customerFedexAccountNumber}
                            onChange={(e) => setCustomerFedexAccountNumber(e.target.value)}
                            placeholder="FedEx Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                        </div>
                    )}
                </>
               )}
            </section>
             <div className="order-actions">
                <button type="submit" disabled={disableAllActions || processing} className="btn btn-gradient btn-shadow-lift btn-success process-order-button-specifics">
                    {processing ? 'Processing Single PO...' : 'PROCESS SINGLE SUPPLIER PO'}
                </button>
            </div>
        </form>
      )}

      {/* Form for Multi-Supplier Mode */}
      {canDisplayProcessingForm && isMultiSupplierMode && !isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form multi-supplier-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="multi-supplier-assignment card">
                <h3>Assign Original Items to Suppliers</h3>
                {originalLineItems.length === 0 && <p>No original line items to assign.</p>}
                {originalLineItems.map((item) => (
                    <div key={`assign-item-${item.line_item_id}`} className="item-assignment-row">
                        <span>({item.quantity}) {item.original_sku || 'N/A'}</span>
                        <select value={lineItemAssignments[item.line_item_id] || ''} onChange={(e) => handleLineItemSupplierAssignment(item.line_item_id, e.target.value)} disabled={disableAllActions || suppliers.length === 0}>
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
                const isFedexBillRecipientMulti = currentPoShipDetails.billToCustomerFedexAccount || false;

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
                        <div className="form-grid shipment-details-multi card-inset">
                            <h5>Shipment Details for this PO (Optional - for Label Generation)</h5>
                            <div className="form-group"> {/* form-group for label-on-top layout */}
                                <label htmlFor={`shipMethod-multi-${supplierId}`}>Method:</label>
                                <select
                                    id={`shipMethod-multi-${supplierId}`}
                                    value={currentPoShipDetails.method || ''}
                                    onChange={(e) => {
                                        const newMethod = e.target.value;
                                        const newSelectedOpt = getSelectedShippingOption(newMethod);
                                        handleMultiSupplierShipmentDetailChange(supplierId, 'method', newMethod);
                                        if (newSelectedOpt?.carrier !== 'fedex') {
                                            handleMultiSupplierShipmentDetailChange(supplierId, 'billToCustomerFedexAccount', false);
                                            handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', '');
                                        } else if (newSelectedOpt?.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account) {
                                            handleMultiSupplierShipmentDetailChange(supplierId, 'billToCustomerFedexAccount', true);
                                            handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', orderData.order.customer_fedex_account_number || '');
                                        }
                                    }}
                                    disabled={disableAllActions}
                                >
                                    <option value="">-- No Label / Method --</option>
                                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={`${opt.value}-${opt.carrier}-multi-${supplierId}`} value={opt.value}>{opt.label}</option>)}
                                </select>
                            </div>
                             {/* Combined Weight and Blind Ship for Multi-Supplier */}
                             <div className="form-group"> {/* Using form-group for label-on-top for weight */}
                                <label htmlFor={`shipWeight-multi-${supplierId}`}>Weight (lbs):</label>
                                <div className="weight-blind-ship-row">
                                    <input 
                                        id={`shipWeight-multi-${supplierId}`} 
                                        type="number" 
                                        className="weight-input-split"
                                        value={currentPoShipDetails.weight || ''} 
                                        onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'weight', e.target.value)} 
                                        step="0.1" 
                                        min="0.1" 
                                        placeholder="e.g., 5.0" 
                                        disabled={disableAllActions || !currentPoShipDetails.method} 
                                    />
                                    {/* Note: Blind ship is global, not per-PO in multi-mode in this implementation */}
                                    {/* If per-PO blind ship is needed, isBlindDropShip state needs to be an object */}
                                </div>
                            </div>
                            {selectedPoShipOption?.carrier === 'fedex' && (
                                <>
                                    <div className="form-group"> {/* Changed to form-group */}
                                        <label htmlFor={`billToCustomerFedexMulti-${supplierId}`}>Bill Customer FedEx:</label>
                                        <input
                                            type="checkbox"
                                            id={`billToCustomerFedexMulti-${supplierId}`}
                                            checked={isFedexBillRecipientMulti}
                                            onChange={(e) => {
                                                handleMultiSupplierShipmentDetailChange(supplierId, 'billToCustomerFedexAccount', e.target.checked);
                                                if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', orderData.order.customer_fedex_account_number);
                                                } else if (!e.target.checked) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', '');
                                                }
                                            }}
                                            disabled={disableAllActions}
                                            // style={{ justifySelf: 'start' }} // Removed as form-group handles block
                                        />
                                    </div>
                                    {isFedexBillRecipientMulti && (
                                        <div className="form-group"> {/* Changed to form-group */}
                                            <label htmlFor={`customerFedexAccountMulti-${supplierId}`}>Cust. FedEx Acct #:</label>
                                            <input
                                                type="text"
                                                id={`customerFedexAccountMulti-${supplierId}`}
                                                value={currentPoShipDetails.customerFedexAccount || ''}
                                                onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', e.target.value)}
                                                placeholder="FedEx Account"
                                                required
                                                disabled={disableAllActions}
                                            />
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                        <div className="form-grid">
                            <label htmlFor={`poNotes-${supplierId}`}>PO Notes for {supplier.name}:</label>
                            <textarea id={`poNotes-${supplierId}`} value={poNotesBySupplier[supplierId] || ''} onChange={(e) => handlePoNotesBySupplierChange(supplierId, e.target.value)} rows="3" disabled={disableAllActions} />
                        </div>
                    </section>
                );
            })}
            <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
                 <h3>Global Options</h3>
                 <div className="form-grid"> {}
                    <label htmlFor="isBlindDropShipMultiGlobal" style={{textAlign: 'right', paddingRight: 'var(--spacing-md)'}}>Blind Ship all?</label>
                    <input
                        type="checkbox"
                        id="isBlindDropShipMultiGlobal"
                        checked={isBlindDropShip}
                        onChange={(e) => setIsBlindDropShip(e.target.checked)}
                        disabled={disableEditableFormFields}
                        style={{ justifySelf: 'start' }}
                    />
                </div>
            </section>
            <div className="order-actions">
                 <button type="submit" disabled={disableAllActions || processing || [...new Set(Object.values(lineItemAssignments))].filter(id => id).length === 0} className="btn btn-gradient btn-shadow-lift btn-success process-order-button-specifics">
                    {processing ? 'Processing Multiple POs...' : 'PROCESS ALL ASSIGNED POs'}
                </button>
            </div>
        </form>
      )}

      {/* Form for G1 Onsite Fulfillment */}
      {canDisplayProcessingForm && isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form g1-onsite-fulfillment-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
          <section className="shipment-info card">
            <h3>Shipment Information</h3>
            <div className="form-grid">
                <label htmlFor="shipmentMethodG1">Method:</label>
                <select 
                    id="shipmentMethodG1" 
                    value={shipmentMethod} 
                    onChange={handleShipmentMethodChange} 
                    disabled={disableEditableFormFields} 
                    required={originalLineItems.length > 0}
                >
                     {SHIPPING_METHODS_OPTIONS.map(opt => <option key={`${opt.value}-${opt.carrier}-g1`} value={opt.value}>{opt.label}</option>)}
                </select>
                
                <label htmlFor="shipmentWeightG1">Weight (lbs):</label>
                <input 
                    type="number" 
                    id="shipmentWeightG1" 
                    className="weight-input-field"
                    value={shipmentWeight} 
                    onChange={handleShipmentWeightChange} 
                    step="0.1" 
                    min="0.1" 
                    placeholder="e.g., 5.0" 
                    required={originalLineItems.length > 0} 
                    disabled={disableEditableFormFields} 
                />

                {/* "Blind Ship?" Label for the grid's first column */}
                <label htmlFor="isBlindDropShipG1" className="blind-ship-grid-label-col1">Blind Ship?</label>
                {/* Empty cell for the grid's second column on this row */}
                <div className="form-grid-empty-cell"></div> 

                {/* Checkbox on a new conceptual row, centered in the first column's space */}
                <div className="blind-ship-checkbox-wrapper-col1"> 
                    <input
                        type="checkbox"
                        id="isBlindDropShipG1" // ID linked from label above
                        className="blind-ship-checkbox-input"
                        checked={isBlindDropShip}
                        onChange={(e) => setIsBlindDropShip(e.target.checked)}
                        disabled={disableEditableFormFields}
                    />
                </div>
                {/* Empty cell for the grid's second column on this checkbox's row */}
                <div className="form-grid-empty-cell"></div>

            </div>
              {currentSelectedShippingOption?.carrier === 'fedex' && originalLineItems.length > 0 && (
                <>
                    <div className="form-grid" style={{marginTop: '10px'}}>
                        <label htmlFor="billToCustomerFedexG1">Bill to Customer's FedEx Account:</label>
                        <input
                        type="checkbox"
                        id="billToCustomerFedexG1"
                        checked={billToCustomerFedex}
                        onChange={(e) => {
                            setBillToCustomerFedex(e.target.checked);
                             if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number);
                            } else if (!e.target.checked) {
                                setCustomerFedexAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                        style={{ justifySelf: 'start' }}
                        />
                    </div>
                    {billToCustomerFedex && (
                        <div className="form-grid" style={{marginTop: '5px'}}>
                        <label htmlFor="customerFedexAccountG1">Customer FedEx Account #:</label>
                        <input
                            type="text"
                            id="customerFedexAccountG1"
                            value={customerFedexAccountNumber}
                            onChange={(e) => setCustomerFedexAccountNumber(e.target.value)}
                            placeholder="FedEx Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                        </div>
                    )}
                </>
               )}
            </section>
            <div className="order-actions">
                <button type="submit" disabled={disableAllActions || processing} className="btn btn-gradient btn-shadow-lift btn-success">
                    {processing ? 'Processing G1 Fulfillment...' : 'PROCESS G1 ONSITE FULFILLMENT'}
                </button>
            </div>
        </form>
      )}

      <div className="manual-actions-section" style={{marginTop: "20px"}}>
           {order && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') && !isActuallyProcessed && (
              <button onClick={() => handleManualStatusUpdate('Completed Offline')} className="btn btn-gradient btn-shadow-lift btn-success manual-action-button-specifics" disabled={disableAllActions}>
                  {manualStatusUpdateInProgress && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
           {order && order.status?.toLowerCase() === 'new' && !isActuallyProcessed && (
              <div style={{ marginTop: '10px', textAlign: 'center' }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); if (!disableAllActions) handleManualStatusUpdate('pending');}}
                      className={`link-button ${(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'link-button-updating' : ''}`}
                      style={{ fontSize: '0.9em', color: !(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'var(--text-secondary)' : undefined }}
                      aria-disabled={disableAllActions || (manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new')}>
                      {(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                  </a>
              </div>
          )}
      </div>

      <div className="order-actions" style={{ marginTop: '20px', textAlign: 'center' }}>
          {(isActuallyProcessed || processSuccess) && (
              <button type="button" onClick={() => navigate('/')} className="btn btn-gradient btn-shadow-lift btn-primary back-to-dashboard-button-specifics" disabled={processing && !processSuccess}>
                  BACK TO DASHBOARD
              </button>
          )}
          {isActuallyProcessed && !processSuccess && (
              <div style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
                  This order has been {order.status?.toLowerCase()} and no further automated actions are available.
              </div>
          )}
      </div>
    </div>
  );
}

export default OrderDetail;