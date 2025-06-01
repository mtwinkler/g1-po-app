// src/components/InternationalOrderProcessor.jsx
import React, { useState, useEffect } from 'react';

const MULTI_SUPPLIER_MODE_VALUE = "_MULTI_SUPPLIER_MODE_";
const G1_ONSITE_INTERNATIONAL_VALUE = "_G1_ONSITE_INTL_";

const SHIPPING_METHODS_OPTIONS_INTL = [
    { value: "07", label: "UPS Worldwide Express", carrier: "ups" },
    { value: "08", label: "UPS Worldwide Expedited", carrier: "ups" },
    { value: "54", label: "UPS Worldwide Express Plus", carrier: "ups" },
    { value: "65", label: "UPS Worldwide Saver", carrier: "ups" },
    { value: "11", label: "UPS Standard", carrier: "ups" },
];

const mapBcShippingToIntlServiceCode = (bcShippingMethod) => {
    if (!bcShippingMethod || typeof bcShippingMethod !== 'string') {
        return null;
    }
    const methodNormalized = bcShippingMethod.toLowerCase().replace(/[^a-z0-9\s]/gi, '').replace(/\s+/g, ' ');
    if (methodNormalized.includes("ups worldwide express plus")) return "54";
    if (methodNormalized.includes("ups worldwide express")) return "07";
    if (methodNormalized.includes("ups worldwide expedited")) return "08";
    if (methodNormalized.includes("ups worldwide saver")) return "65";
    if (methodNormalized.includes("ups standard")) return "11";
    if (methodNormalized.includes("worldwide express plus")) return "54";
    if (methodNormalized.includes("worldwide express")) return "07";
    if (methodNormalized.includes("worldwide expedited")) return "08";
    if (methodNormalized.includes("worldwide saver")) return "65";
    if (methodNormalized.includes("standard")) return "11";
    console.warn(`InternationalOrderProcessor: Could not map BigCommerce shipping method "${bcShippingMethod}" (normalized: "${methodNormalized}") to a known UPS international service code.`);
    return null;
};

// Helper function to format payment method strings
const formatPaymentMethod = (paymentMethodString) => {
  if (typeof paymentMethodString !== 'string') {
    return ''; // Return empty string for non-string inputs
  }
  const bracketIndex = paymentMethodString.indexOf(" [");
  if (bracketIndex !== -1) {
    // If " [" is found, return the substring before it
    return paymentMethodString.substring(0, bracketIndex);
  }
  // If " [" is not found, return the original string
  return paymentMethodString;
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

function InternationalOrderProcessor({
    orderData,
    suppliers,
    apiService,
    setProcessError,
    onSuccessRefresh
}) {
  if (!orderData || !orderData.order || !orderData.order.id) {
    console.warn("InternationalOrderProcessor: orderData, orderData.order, or orderData.order.id is not available at render time. Props:", { orderData });
    return <p className="loading-message">Loading order data or required order information is missing...</p>;
  }

  const { order, line_items: originalLineItemsFromData = [], billing_address = {} } = orderData;
  const orderId = order.id;
  const cleanPullSuffix = " - clean pull";
  const originalLineItems = originalLineItemsFromData || [];

  const [internationalApiDetails, setInternationalApiDetails] = useState(null);
  const [loadingApiDetails, setLoadingApiDetails] = useState(true);
  const [apiDetailsError, setApiDetailsError] = useState(null);
  const [dynamicComplianceValues, setDynamicComplianceValues] = useState({});
  const [exemptions, setExemptions] = useState({});
  const [editableCustomsItems, setEditableCustomsItems] = useState([]);
  const [selectedFulfillmentStrategy, setSelectedFulfillmentStrategy] = useState('');
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [singleOrderPoNotes, setSingleOrderPoNotes] = useState('');
  const [isBlindDropShip, setIsBlindDropShip] = useState(false);
  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);
  const [profitInfo, setProfitInfo] = useState({ isCalculable: false });
  const [shipmentWeight, setShipmentWeight] = useState('1');
  const [selectedShippingService, setSelectedShippingService] = useState('');
  const [descriptionOfGoods, setDescriptionOfGoods] = useState('');
  const [paymentType, setPaymentType] = useState('01'); // UPS Payment Type Code: 01 for Bill Shipper, 02 for Bill Receiver etc.

  // New state for billing option
  const [selectedBillingOption, setSelectedBillingOption] = useState(''); 
  const [customerUpsAccountNumber, setCustomerUpsAccountNumber] = useState('');
  const [customerUpsAccountZipCode, setCustomerUpsAccountZipCode] = useState('');

  const [isProcessingOrder, setIsProcessingOrder] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(false);
  const [newShipmentInfo, setNewShipmentInfo] = useState({
      poNumber: null, trackingNumber: null, labelUrl: null,
      poPdfUrl: null, packingSlipPdfUrl: null
  });

  const customComponentStyles = `
    :root {
      --h3-glow-color-light: rgba(0, 86, 179, 0.25); /* Subtle primary color glow for light mode */
      --h3-glow-color-dark: rgba(230, 230, 230, 0.35); /* Lighter glow for dark mode */
    }

    .international-order-processor h3 {
      font-size: 1.25em;
      text-transform: uppercase;
      letter-spacing: 1px;
      /* Default to light mode glow, will be overridden by dark mode media query if active */
      text-shadow: 0 0 6px var(--h3-glow-color-light); 
    }

    @media (max-width: 768px) {
      .international-order-processor .editable-customs-table thead th { display: none; }
      .international-order-processor .editable-customs-table tbody td { padding-top: 0.5rem; padding-bottom: 0.5rem; }
      .international-order-processor .editable-customs-table tbody td input[type="text"] { width: 100%; box-sizing: border-box; }
    }
    
    @media (prefers-color-scheme: dark) {
      .international-order-processor h3 {
        text-shadow: 0 0 6px var(--h3-glow-color-dark);
      }
      @media (max-width: 768px) {
        .international-order-processor .customs-items-table tr { background-color: #363636; } /* Lighter card for customs items rows */
        .international-order-processor .customs-items-table td { padding-left: 3%; } /* Indent content a bit */
      }
    }
    
    /* Light mode specific adjustments if needed, for now it inherits from --form-page-bg or card defaults */
    @media (prefers-color-scheme: light) {
       /* .international-order-processor h3 { text-shadow: 0 0 6px var(--h3-glow-color-light); } // Already default */
      @media (max-width: 768px) { 
        /* .international-order-processor .customs-data-section-card { background-color: #ffffff; } */ 
      }
    }
  `;

  useEffect(() => {
    const fetchInternationalDetailsFromApi = async () => {
      if (apiService) {
        setLoadingApiDetails(true);
        setApiDetailsError(null);
        try {
          const details = await apiService.get(`/order/${orderId}/international-details`);
          setInternationalApiDetails(details);
          setEditableCustomsItems(details?.line_items_customs_info?.map(item => ({ ...item })) || []);
          const initialValues = {};
          const initialExemptions = {};
          if (details?.required_compliance_fields) {
            details.required_compliance_fields.forEach(field => {
              const fieldKey = field.field_label;
              if (field.id_owner === 'Shipper' && details.shipper_ein) initialValues[fieldKey] = details.shipper_ein;
              else if (order.compliance_info?.[fieldKey] !== undefined) initialValues[fieldKey] = order.compliance_info[fieldKey];
              else initialValues[fieldKey] = '';
              if (field.has_exempt_option) initialExemptions[fieldKey] = (order.compliance_info?.[fieldKey] === 'EXEMPT');
            });
          }
          setDynamicComplianceValues(initialValues);
          setExemptions(initialExemptions);
        } catch (err) {
          const errorMsg = err.data?.message || err.message || "Failed to load detailed international order data.";
          setApiDetailsError(errorMsg);
          if (setProcessError) setProcessError(errorMsg);
        } finally {
          setLoadingApiDetails(false);
        }
      }
    };

    fetchInternationalDetailsFromApi();

    // Set default billing option based on order data
    if (order.is_bill_to_customer_account) {
        setSelectedBillingOption("recipient");
        setCustomerUpsAccountNumber(order.customer_ups_account_number || '');
        const bZip = billing_address?.zip || order.customer_billing_zip;
        setCustomerUpsAccountZipCode(bZip ? String(bZip).replace(/\s+/g, '') : '');
    } else {
        setSelectedBillingOption("g1_account");
        setCustomerUpsAccountNumber(''); 
        setCustomerUpsAccountZipCode('');
    }
    
    let methodStringToMap = order.customer_shipping_method;
    if (order.is_bill_to_customer_account && order.customer_selected_freight_service) {
        methodStringToMap = order.customer_selected_freight_service;
    }
    const mappedServiceCode = mapBcShippingToIntlServiceCode(methodStringToMap);
    if (mappedServiceCode) setSelectedShippingService(mappedServiceCode);
    else if (SHIPPING_METHODS_OPTIONS_INTL.length > 0) {
        setSelectedShippingService(SHIPPING_METHODS_OPTIONS_INTL[0].value);
        if (methodStringToMap) console.warn(`InternationalOrderProcessor: Could not map shipping method "${methodStringToMap}". Defaulting.`);
    } else setSelectedShippingService('');

  }, [orderId, order, apiService, setProcessError, billing_address?.zip]);


  useEffect(() => {
    let determinedShipmentDesc = "Computer Components"; 
    const commonSuffix = " for computers";
    const characterLimit = 50;
    if (editableCustomsItems && editableCustomsItems.length > 0) {
        const customsDescriptions = editableCustomsItems.map(item => item.customs_description?.trim()).filter(Boolean);
        const uniqueDescriptions = [...new Set(customsDescriptions)];
        if (uniqueDescriptions.length === 1) determinedShipmentDesc = uniqueDescriptions[0];
        else if (uniqueDescriptions.length > 1) {
            const strippedDescriptions = uniqueDescriptions.map(desc => desc.toLowerCase().endsWith(commonSuffix.toLowerCase()) ? desc.substring(0, desc.length - commonSuffix.length).trim() : desc);
            let joinedStripped = strippedDescriptions.join(', ');
            if ((joinedStripped + commonSuffix).length <= characterLimit) determinedShipmentDesc = joinedStripped + commonSuffix;
            else if (joinedStripped.length <= characterLimit) determinedShipmentDesc = joinedStripped;
            else {
                let currentDesc = "";
                for (let i = 0; i < strippedDescriptions.length; i++) {
                    const nextDescPart = strippedDescriptions[i];
                    const separator = currentDesc ? ", " : "";
                    if ((currentDesc + separator + nextDescPart).length <= characterLimit) currentDesc += separator + nextDescPart;
                    else { if (i === 0 && nextDescPart.length > characterLimit) currentDesc = nextDescPart.substring(0, characterLimit - 3) + "..."; break; }
                }
                if (currentDesc) determinedShipmentDesc = currentDesc;
                else if (strippedDescriptions[0]) determinedShipmentDesc = strippedDescriptions[0].substring(0, characterLimit -3) + "...";
            }
        } else if (originalLineItems?.[0]?.line_item_name || originalLineItems?.[0]?.name) determinedShipmentDesc = originalLineItems[0].line_item_name || originalLineItems[0].name;
    } else if (originalLineItems?.[0]?.line_item_name || originalLineItems?.[0]?.name) determinedShipmentDesc = originalLineItems[0].line_item_name || originalLineItems[0].name;
    setDescriptionOfGoods(String(determinedShipmentDesc || 'Assorted Goods').substring(0, characterLimit));
  }, [editableCustomsItems, originalLineItems]);


  useEffect(() => {
    const isSupplierPOSelected = selectedFulfillmentStrategy && selectedFulfillmentStrategy !== "" && selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE && !isNaN(parseInt(selectedFulfillmentStrategy, 10));
    if (isSupplierPOSelected) {
        const supplierId = parseInt(selectedFulfillmentStrategy, 10);
        const supplier = suppliers.find(s => s.id === supplierId);
        setSingleOrderPoNotes(supplier?.defaultponotes || '');
        setPurchaseItems(originalLineItems.map(item => ({
            original_order_line_item_id: item.line_item_id, sku: item.hpe_option_pn || item.original_sku || '',
            description: (item.hpe_po_description || item.line_item_name || '') + ((item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
            skuInputValue: item.hpe_option_pn || item.original_sku || '', quantity: item.quantity || 1, unit_cost: '', condition: 'New',
            original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn, original_name: item.line_item_name,
            hpe_po_description: item.hpe_po_description, hpe_pn_type: item.hpe_pn_type,
        })));
    } else { setPurchaseItems([]); setSingleOrderPoNotes(''); }
  }, [originalLineItems, selectedFulfillmentStrategy, suppliers, cleanPullSuffix]);

  useEffect(() => {
    if (!apiService || !debouncedSku || skuToLookup.index === -1) return;
    const isSupplierPOSelected = selectedFulfillmentStrategy && selectedFulfillmentStrategy !== "" && selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE && !isNaN(parseInt(selectedFulfillmentStrategy, 10));
    if (!isSupplierPOSelected) return;
    const abortController = new AbortController();
    const fetchDescription = async () => {
      try {
        const data = await apiService.get(`/lookup/description/${encodeURIComponent(String(debouncedSku).trim())}`);
        if (abortController.signal.aborted) return;
        setPurchaseItems(prevItems => {
            const updatedItems = [...prevItems];
            if (updatedItems[skuToLookup.index]?.skuInputValue === debouncedSku) {
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) newDescription += cleanPullSuffix;
                else if (!newDescription) {
                    const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDesc ? `${existingDesc} ` : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(` ${cleanPullSuffix.trim()}`)) newDescription = cleanPullSuffix.trim();
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
            }
            return updatedItems;
        });
      } catch (error) { if (error.name !== 'AbortError' && error.status !== 401 && error.status !== 403) console.error("Error fetching SKU description:", error); }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, apiService, selectedFulfillmentStrategy]);

  useEffect(() => {
    const revenue = originalLineItems.reduce((sum, item) => sum + (parseFloat(item.sale_price || 0) * parseInt(item.quantity || 0, 10)), 0);
    let cost = 0; let isCalculable = false;
    const isSupplierPOSelected = selectedFulfillmentStrategy && selectedFulfillmentStrategy !== "" && selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE && !isNaN(parseInt(selectedFulfillmentStrategy, 10));
    if (isSupplierPOSelected) {
        if (purchaseItems.length > 0) {
            if (purchaseItems.every(item => item.unit_cost !== undefined && item.unit_cost !== '' && !isNaN(parseFloat(item.unit_cost)))) {
                cost = purchaseItems.reduce((total, item) => total + (parseFloat(item.unit_cost) * parseInt(item.quantity, 10)), 0);
                isCalculable = true;
            }
        } else if (originalLineItems.length === 0) { isCalculable = true; cost = 0; }
    } else if (selectedFulfillmentStrategy === G1_ONSITE_INTERNATIONAL_VALUE) { cost = 0; isCalculable = originalLineItems.length > 0 || revenue > 0; }
    else isCalculable = false;
    if (isCalculable) {
        const profit = revenue - cost; const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
        setProfitInfo({ totalRevenue: revenue, totalCost: cost, profitAmount: profit, profitMargin: margin, isCalculable: true });
    } else setProfitInfo({ isCalculable: false, totalRevenue: revenue, totalCost:0, profitAmount:0, profitMargin:0 });
  }, [originalLineItems, purchaseItems, selectedFulfillmentStrategy]);

  const handleEditableCustomsItemChange = (index, field, value) => setEditableCustomsItems(prev => prev.map((item, i) => i === index ? { ...item, [field]: value } : item));
  const handleFulfillmentStrategyChange = (e) => { setSelectedFulfillmentStrategy(e.target.value); if(setProcessError) setProcessError(null); setProcessSuccess(false); setApiDetailsError(null); };
  const handlePurchaseItemChange = (index, field, value) => setPurchaseItems(prev => prev.map((item, i) => { if (i === index) { const newItem = { ...item, [field]: value }; if (field === 'skuInputValue') { const trimmedSku = String(value).trim(); newItem.skuInputValue = trimmedSku; newItem.sku = trimmedSku; setSkuToLookup({ index, sku: trimmedSku }); } return newItem; } return item; }));
  const handleDynamicComplianceChange = (fieldName, value) => setDynamicComplianceValues(prev => ({ ...prev, [fieldName]: value }));
  const handleExemptionChange = (fieldName, isChecked) => { setExemptions(prev => ({ ...prev, [fieldName]: isChecked })); handleDynamicComplianceChange(fieldName, isChecked ? 'EXEMPT' : (order.compliance_info?.[fieldName] || '')); };
  const handleBrandingChange = (event) => setIsBlindDropShip(event.target.value === 'blind');

  const handleProcessCombinedOrder = async () => {
    if(setProcessError) setProcessError(null);
    setIsProcessingOrder(true);
    setProcessSuccess(false);
    setNewShipmentInfo({ poNumber: null, trackingNumber: null, labelUrl: null, poPdfUrl: null, packingSlipPdfUrl: null });
    let poDataPayload = null;
    if (!internationalApiDetails) { if(setProcessError) setProcessError("International details not loaded."); setIsProcessingOrder(false); return; }
    if (!shipmentWeight || parseFloat(shipmentWeight) <= 0) { if(setProcessError) setProcessError("Shipment weight must be > 0."); setIsProcessingOrder(false); return; }
    if (!selectedShippingService) { if(setProcessError) setProcessError("Select an international shipping service."); setIsProcessingOrder(false); return; }
    if (!descriptionOfGoods.trim()) { if(setProcessError) setProcessError("Provide a shipment description."); setIsProcessingOrder(false); return; }
    if (selectedBillingOption === "recipient" && (!customerUpsAccountNumber.trim() || !customerUpsAccountZipCode.trim())) { if(setProcessError) setProcessError("Recipient UPS Acct # and Postal Code are required for Bill Recipient."); setIsProcessingOrder(false); return; }

    const isSupplierPOSelected = selectedFulfillmentStrategy && selectedFulfillmentStrategy !== "" && selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE && !isNaN(parseInt(selectedFulfillmentStrategy, 10));
    if (isSupplierPOSelected) {
        if (purchaseItems.length === 0 && originalLineItems.length > 0) { if(setProcessError) setProcessError("No PO items configured."); setIsProcessingOrder(false); return; }
        let itemValidationError = null;
        const finalPoLineItems = purchaseItems.map((item, index) => {
            const qtyInt = parseInt(item.quantity, 10), costFlt = parseFloat(item.unit_cost);
            if (isNaN(qtyInt) || qtyInt <= 0) { itemValidationError = `PO Item #${index + 1}: Qty > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFlt) || costFlt < 0) { itemValidationError = `PO Item #${index + 1}: Unit cost invalid.`; return null; }
            if (!String(item.sku).trim()) { itemValidationError = `PO Item #${index + 1}: SKU required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `PO Item #${index + 1}: Desc required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.sku).trim(), description: String(item.description).trim(), quantity: qtyInt, unitCost: costFlt.toFixed(2) };
        }).filter(Boolean);
        if (itemValidationError) { if(setProcessError) setProcessError(itemValidationError); setIsProcessingOrder(false); return; }
        if (finalPoLineItems.length === 0 && originalLineItems.length > 0) { if(setProcessError) setProcessError("No valid PO line items."); setIsProcessingOrder(false); return; }
        if (finalPoLineItems.length > 0 || (originalLineItems.length === 0 && purchaseItems.length === 0)) poDataPayload = { supplierId: parseInt(selectedFulfillmentStrategy, 10), poNotes: singleOrderPoNotes, lineItems: finalPoLineItems, is_blind_drop_ship: isBlindDropShip };
        else if (originalLineItems.length > 0 && finalPoLineItems.length === 0) { if(setProcessError) setProcessError("Cannot create empty PO with original items."); setIsProcessingOrder(false); return; }
    }

    const shipperDetails = { Name: "Global One Technology", AttentionName: "Order Fulfillment", TaxIdentificationNumber: internationalApiDetails.shipper_ein, Phone: { Number: "8774183246" }, Address: { AddressLine: ["4916 S 184th Plaza"], City: "Omaha", StateProvinceCode: "NE", PostalCode: "68135", CountryCode: "US" }, ShipperNumber: "EW1847" };
    let paymentInformationPayload;
    if (selectedBillingOption === "recipient") {
        paymentInformationPayload = { ShipmentCharge: { Type: "02", BillReceiver: { AccountNumber: customerUpsAccountNumber.trim(), Address: { PostalCode: customerUpsAccountZipCode.trim().replace(/\s+/g, ''), CountryCode: order.customer_shipping_country_iso2.toUpperCase() }}} }; // Type 02 for Bill Receiver
    } else { // "g1_account"
        paymentInformationPayload = { ShipmentCharge: { Type: "01", BillShipper: { AccountNumber: "EW1847" } } }; // Type 01 for Bill Shipper
    }

    let shipToName = (order.customer_company || `${order.customer_shipping_first_name || ''} ${order.customer_shipping_last_name || ''}`.trim() || "Receiver").substring(0,35);
    let shipToAttentionName = (`${order.customer_shipping_first_name || ''} ${order.customer_shipping_last_name || ''}`.trim() || order.customer_name || shipToName || "Receiving Dept").substring(0,35);
    if (!shipToAttentionName) shipToAttentionName = shipToName;
    const finalComplianceValues = {...dynamicComplianceValues}; Object.keys(exemptions).forEach(key => { if (exemptions[key]) finalComplianceValues[key] = 'EXEMPT'; });
    const receiverTaxField = internationalApiDetails?.required_compliance_fields?.find(f => f.id_owner === 'Receiver' && finalComplianceValues[f.field_label] && finalComplianceValues[f.field_label] !== 'EXEMPT');
    const shipToTaxId = receiverTaxField ? finalComplianceValues[receiverTaxField.field_label] : '';
    let totalInvoiceMonetaryValue = parseFloat(originalLineItems.reduce((sum, item) => sum + (parseFloat(item.sale_price || 0) * parseInt(item.quantity || 0, 10)), 0).toFixed(2));
    let invoiceLineTotalObject = totalInvoiceMonetaryValue >= 1.00 ? { CurrencyCode: "USD", MonetaryValue: totalInvoiceMonetaryValue.toFixed(2) } : null;

    const shipmentObject = {
        Description: descriptionOfGoods, Shipper: shipperDetails,
        ShipTo: { Name: shipToName, AttentionName: shipToAttentionName, TaxIdentificationNumber: shipToTaxId, Phone: { Number: order.customer_phone ? String(order.customer_phone).replace(/\D/g, '') : undefined }, Address: { AddressLine: [order.customer_shipping_address_line1, order.customer_shipping_address_line2].filter(Boolean), City: order.customer_shipping_city, PostalCode: order.customer_shipping_zip, CountryCode: order.customer_shipping_country_iso2, ...( (order.customer_shipping_country_iso2?.toUpperCase() === 'US' || order.customer_shipping_country_iso2?.toUpperCase() === 'CA') && order.customer_shipping_state && { StateProvinceCode: order.customer_shipping_state }) } },
        PaymentInformation: paymentInformationPayload, Service: { Code: selectedShippingService },
        Package: { Description: "Assorted Goods", Packaging: { Code: "02" }, PackageWeight: { UnitOfMeasurement: { Code: "LBS" }, Weight: String(shipmentWeight) }, },
        ShipmentServiceOptions: { InternationalForms: { FormType: "01", CurrencyCode: "USD", Product: editableCustomsItems.map(item => { const origItem = originalLineItems.find(oli => oli.line_item_id === item.original_order_line_item_id); return { Description: item.customs_description ? item.customs_description.substring(0, 35) : 'N/A', CommodityCode: item.harmonized_tariff_code, OriginCountryCode: item.default_country_of_origin, Unit: { Number: String(item.quantity), Value: String(parseFloat(origItem?.sale_price || '0.00').toFixed(2)), CurrencyCode: "USD", UnitOfMeasurement: { Code: "PCS" } }, }; }), InvoiceDate: new Date().toISOString().split('T')[0].replace(/-/g, ''), InvoiceNumber: String(order.bigcommerce_order_id || order.id), ReasonForExport: "SALE", Contacts: { SoldTo: {} } } }
    };
    const destCountryUpper = order?.customer_shipping_country_iso2?.toUpperCase();
    if (invoiceLineTotalObject) { if (destCountryUpper === 'CA' || destCountryUpper === 'PR') shipmentObject.InvoiceLineTotal = invoiceLineTotalObject; else if (shipmentObject.ShipmentServiceOptions?.InternationalForms) shipmentObject.ShipmentServiceOptions.InternationalForms.InvoiceLineTotal = invoiceLineTotalObject; }
    else if (destCountryUpper === 'CA' || destCountryUpper === 'PR') console.error(`ERROR: InvoiceLineTotal required for ${destCountryUpper} but value < $1.00.`);
    const shipmentRequestPayload = { ShipmentRequest: { Request: { RequestOption: "nonvalidate", TransactionReference: { CustomerContext: `Order-${order.bigcommerce_order_id || order.id}` } }, Shipment: shipmentObject, LabelSpecification: { LabelImageFormat: { Code: "GIF" } } } };
    const currentBillingAddr = billing_address || {};
    let soldToName = (currentBillingAddr.company || (`${currentBillingAddr.first_name || ''} ${currentBillingAddr.last_name || ''}`).trim() || order.customer_name || order.customer_company || "Customer").substring(0,35);
    let soldToAttnName = (order.customer_name || soldToName || "Customer Contact").substring(0,35);
    const soldToPh = (currentBillingAddr.phone ? String(currentBillingAddr.phone).replace(/\D/g, '') : '') || (order.customer_phone ? String(order.customer_phone).replace(/\D/g, '') : undefined);
    shipmentRequestPayload.ShipmentRequest.Shipment.ShipmentServiceOptions.InternationalForms.Contacts.SoldTo = { Name: soldToName, AttentionName: soldToAttnName, Phone: { Number: soldToPh }, Address: { AddressLine: [currentBillingAddr.street_1, currentBillingAddr.street_2].filter(Boolean).length > 0 ? [currentBillingAddr.street_1, currentBillingAddr.street_2].filter(Boolean) : shipmentObject.ShipTo.Address.AddressLine, City: currentBillingAddr.city || shipmentObject.ShipTo.Address.City, ...( ( (currentBillingAddr.country_iso2 || order.customer_shipping_country_iso2)?.toUpperCase() === 'US' || (currentBillingAddr.country_iso2 || order.customer_shipping_country_iso2)?.toUpperCase() === 'CA') && (currentBillingAddr.state || order.customer_shipping_state) && { StateProvinceCode: currentBillingAddr.state || order.customer_shipping_state }), PostalCode: currentBillingAddr.zip || shipmentObject.ShipTo.Address.PostalCode, CountryCode: currentBillingAddr.country_iso2 || shipmentObject.ShipTo.Address.CountryCode, } };
    const finalShipmentDataPayload = { ...shipmentRequestPayload, is_blind_drop_ship: isBlindDropShip };
    const finalCombinedPayload = { po_data: poDataPayload, shipment_data: finalShipmentDataPayload };

    try {
        const result = await apiService.post(`/order/${orderId}/process-international-dropship`, finalCombinedPayload);
        setNewShipmentInfo({ poNumber: result.poNumber, trackingNumber: result.trackingNumber, labelUrl: result.labelUrl, poPdfUrl: result.poPdfUrl, packingSlipPdfUrl: result.packingSlipPdfUrl });
        setProcessSuccess(true); if (onSuccessRefresh) onSuccessRefresh();
    } catch (err) { const errorMsg = err.data?.message || err.message || "Failed to process intl order."; if(setProcessError) setProcessError(errorMsg); setProcessSuccess(false); }
    finally { setIsProcessingOrder(false); }
  };
  
  if (loadingApiDetails && !internationalApiDetails && !editableCustomsItems.length) return <p className="loading-message">Loading international shipping details...</p>;
  if (apiDetailsError && !loadingApiDetails) return <div className="error-message card" style={{margin: '20px', padding: '20px'}}>Error loading international details: {apiDetailsError}</div>;

  const disableFormFields = isProcessingOrder || processSuccess;
  const isSupplierPOFlow = selectedFulfillmentStrategy && selectedFulfillmentStrategy !== "" && selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE && !isNaN(parseInt(selectedFulfillmentStrategy, 10));

  return (
    <div className="international-order-processor">
      <style>{customComponentStyles}</style>
      <section className="card">
        <h3>Int'l Order Info</h3>
        <p><strong>Destination:</strong> {internationalApiDetails?.country_name || order.customer_shipping_country} ({order.customer_shipping_country_iso2 || 'N/A'})</p>
        {order.compliance_info && Object.keys(order.compliance_info).length > 0 && (<div className="captured-compliance-ids card-inset"><h4>Captured Compliance IDs (from Checkout)</h4><ul>{Object.entries(order.compliance_info).map(([key, value]) => (<li key={`checkout-${key}`}><strong>{key}:</strong> {String(value)}</li>))}</ul></div>)}
        {(!order.compliance_info || Object.keys(order.compliance_info).length === 0) && (<p style={{marginTop: 'var(--spacing-md)'}}>No specific compliance IDs were captured from checkout.</p>)}
      </section>

      {internationalApiDetails && (
        <section className="card customs-data-section-card" style={{marginTop: 'var(--spacing-lg)'}}>
            <h3>Customs & Compliance</h3>
            {internationalApiDetails.required_compliance_fields?.length > 0 && (
            <div className="form-section">
                <h5>Required Tax/Compliance IDs for {internationalApiDetails.country_name || order.customer_shipping_country}:</h5>
                <div className="form-grid compliance-form-grid">
                {internationalApiDetails.required_compliance_fields.map(field => {
                    const fieldKey = field.field_label; const isShipperOwned = field.id_owner === 'Shipper';
                    const inputValue = isShipperOwned ? internationalApiDetails.shipper_ein : (dynamicComplianceValues[fieldKey] || '');
                    return (<React.Fragment key={fieldKey}><label htmlFor={`compliance-${fieldKey.replace(/\s+/g, '-')}`}>{field.field_label}{field.is_required && !isShipperOwned ? '*' : ''}:</label><div className="compliance-input-group"><input type="text" id={`compliance-${fieldKey.replace(/\s+/g, '-')}`} value={inputValue} onChange={(e) => !isShipperOwned && handleDynamicComplianceChange(fieldKey, e.target.value)} readOnly={isShipperOwned || (field.has_exempt_option && exemptions[fieldKey])} placeholder={isShipperOwned ? '' : field.field_label} style={(isShipperOwned || (field.has_exempt_option && exemptions[fieldKey])) ? {backgroundColor: 'var(--bg-disabled)'} : {}} />{field.has_exempt_option && !isShipperOwned && (<div className="exempt-checkbox-group"><input type="checkbox" id={`exempt-${fieldKey.replace(/\s+/g, '-')}`} checked={exemptions[fieldKey] || false} onChange={(e) => handleExemptionChange(fieldKey, e.target.checked)} /><label htmlFor={`exempt-${fieldKey.replace(/\s+/g, '-')}`} className="exempt-label">Exempt</label></div>)}</div></React.Fragment>);
                })}</div></div>)}
            {editableCustomsItems.length > 0 && (
            <div className="form-section"><h5>Customs Information per Item (Editable)</h5><div className="customs-items-table-container">
            <table className="customs-items-table editable-customs-table"><thead><tr><th>SKU</th><th>Qty</th><th>Name</th><th>Customs Desc.*</th><th>Tariff*</th><th>COO*</th></tr></thead>
                <tbody>{editableCustomsItems.map((item, index) => (
                    <tr key={item.original_order_line_item_id}><td><b>{item.sku}</b></td><td><b>Qty {item.quantity}</b></td><td>{item.product_name}</td>
                        <td><input type="text" value={item.customs_description || ''} onChange={(e) => handleEditableCustomsItemChange(index, 'customs_description', e.target.value)} disabled={disableFormFields} maxLength={35} placeholder="Description"/></td>
                        <td><input type="text" value={item.harmonized_tariff_code || ''} onChange={(e) => handleEditableCustomsItemChange(index, 'harmonized_tariff_code', e.target.value)} disabled={disableFormFields} placeholder="Tariff Code"/></td>
                        <td><input type="text" value={item.default_country_of_origin || ''} onChange={(e) => handleEditableCustomsItemChange(index, 'default_country_of_origin', e.target.value.toUpperCase())} disabled={disableFormFields} maxLength={2} style={{textTransform: 'uppercase'}} placeholder="US"/></td>
                    </tr>))}</tbody></table></div></div>)}</section>)}

      <section className="supplier-mode-selection card" style={{marginTop: 'var(--spacing-lg)'}}>
        <h3>Order Fulfillment Mode</h3><div className="form-grid"><label htmlFor="mainSupplierTrigger">Fulfillment Type:</label><select id="fulfillmentStrategy" value={selectedFulfillmentStrategy} onChange={handleFulfillmentStrategyChange} disabled={disableFormFields} required><option value="" disabled>-- Select Fulfillment Strategy --</option>{suppliers && suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}<option value={G1_ONSITE_INTERNATIONAL_VALUE}>* G1 Onsite Fulfillment *</option></select></div>
        <p className="info-text card-inset" style={{marginTop:'var(--spacing-sm)'}}></p></section>

      {isSupplierPOFlow && (<section className="purchase-info card"><h3>Create PO for {suppliers.find(s=>s.id === parseInt(selectedFulfillmentStrategy, 10))?.name}</h3><div className="form-grid"><label htmlFor="singlePoNotes">PO Notes/Payment Instructions:</label><textarea id="singlePoNotes" value={singleOrderPoNotes} onChange={(e) => setSingleOrderPoNotes(e.target.value)} rows="3" disabled={disableFormFields} /></div>
            <div className="purchase-items-grid"><h4>Items to Purchase for PO:</h4><div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                {purchaseItems.map((item, index) => (<div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row"><div><label className="mobile-label">SKU:</label><input type="text" value={item.skuInputValue || ''} onChange={(e) => handlePurchaseItemChange(index, 'skuInputValue', e.target.value)} placeholder="SKU" required disabled={disableFormFields} title={item.original_sku ? `Original: ${item.original_sku}` : ''} className="sku-input" /></div><div><label className="mobile-label">Desc:</label><textarea value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableFormFields} className="description-textarea" /></div><div className="qty-cost-row"><div><label className="mobile-label">Qty:</label><input type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableFormFields} className="qty-input" /></div><div><label className="mobile-label">Cost:</label><input type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableFormFields} className="price-input" /></div></div></div>))}</div></section>)}
      {isSupplierPOFlow && profitInfo.isCalculable && (<ProfitDisplay info={profitInfo} />)}

      <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
          <h3>Shipment Details</h3>
          <div className="form-grid">
              <label htmlFor="shipmentDescription">Overall Shipment Description*:</label><input type="text" id="shipmentDescription" value={descriptionOfGoods} onChange={(e) => setDescriptionOfGoods(e.target.value.substring(0,50))} placeholder="e.g., Computer Parts" required disabled={disableFormFields} maxLength={50}/>
              <label htmlFor="intlShipmentWeight">Total Shipment Weight (lbs)*:</label><input type="number" id="intlShipmentWeight" placeholder="e.g., 10.5" step="0.1" min="0.1" value={shipmentWeight} onChange={(e) => setShipmentWeight(e.target.value)} required disabled={disableFormFields}/>
              <label htmlFor="intlShippingService">International Shipping Service*:</label><select id="intlShippingService" value={selectedShippingService} onChange={(e) => setSelectedShippingService(e.target.value)} required disabled={disableFormFields}><option value="">-- Select Service --</option>{SHIPPING_METHODS_OPTIONS_INTL.map(opt => ( <option key={opt.value} value={opt.value}>{opt.label}</option> ))}</select>
              
              {/* Billing Option Dropdown */}
              <label htmlFor="billingOptionIntl">Billing Option*:</label>
              <select id="billingOptionIntl" value={selectedBillingOption} onChange={(e) => {
                  setSelectedBillingOption(e.target.value);
                  if (e.target.value === "recipient") {
                      setCustomerUpsAccountNumber(order?.customer_ups_account_number || '');
                      const bZip = billing_address?.zip || order?.customer_billing_zip;
                      setCustomerUpsAccountZipCode(bZip ? String(bZip).replace(/\s+/g, '') : '');
                  } else { // "g1_account"
                      setCustomerUpsAccountNumber('');
                      setCustomerUpsAccountZipCode('');
                  }}}
                  disabled={disableFormFields} required >
                  <option value="" disabled>-- Select Billing Option --</option>
                  <option value="g1_account">Ship on G1 Account</option>
                  <option value="recipient">Bill to Recipient Account</option>
              </select>

              {selectedBillingOption === "recipient" && (<>
                  <label htmlFor="customerUpsAccountIntl">Recipient UPS Acct #*:</label>
                  <input type="text" id="customerUpsAccountIntl" value={customerUpsAccountNumber} onChange={(e) => setCustomerUpsAccountNumber(e.target.value)} placeholder="Recipient's UPS Account Number" required disabled={disableFormFields}/>
                  <label htmlFor="customerUpsAccZipIntl">Recipient Acct Postal Code*:</label>
                  <input type="text" id="customerUpsAccZipIntl" value={customerUpsAccountZipCode} onChange={(e) => setCustomerUpsAccountZipCode(e.target.value.replace(/\s+/g, ''))} placeholder="Account Postal Code (no spaces)" required disabled={disableFormFields}/>
              </>)}

              <label htmlFor="brandingOption">Packing Slip Branding:</label><select id="brandingOption" value={isBlindDropShip ? 'blind' : 'g1'} onChange={handleBrandingChange} disabled={disableFormFields}><option value="g1">Global One Technology Branding</option><option value="blind">Blind Ship (Generic Packing Slip)</option></select>
          </div>
      </section>

      <div className="order-actions" style={{ marginTop: 'var(--spacing-lg)'}}>
          {processSuccess ? (<div className="success-message-box"><h4>Order Processed Successfully!</h4>{newShipmentInfo.poNumber && <p><strong>PO Number:</strong> {newShipmentInfo.poNumber}</p>}{newShipmentInfo.trackingNumber && <p><strong>Tracking Number:</strong> {newShipmentInfo.trackingNumber}</p>}</div>
          ) : (
              <button type="button" className="process-order-button" onClick={handleProcessCombinedOrder}
                  disabled={ loadingApiDetails || isProcessingOrder || !internationalApiDetails || !shipmentWeight || !selectedShippingService || !selectedFulfillmentStrategy || !selectedBillingOption || (selectedBillingOption === 'recipient' && (!customerUpsAccountNumber.trim() || !customerUpsAccountZipCode.trim())) }>
                  {isProcessingOrder ? 'Processing...' : (isSupplierPOFlow ? 'Process PO/Shipment' : 'Process Shipment')}
              </button>
          )}
      </div>
    </div>
  );
}

export default InternationalOrderProcessor;
