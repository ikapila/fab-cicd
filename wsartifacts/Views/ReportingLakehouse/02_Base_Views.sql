-- ----------------------------------------------------------
-- View: vw_additional_charges_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_additional_charges_detail
AS
SELECT 
    a.sequence_number 
    ,a.sundry_charge_amount AS charges 
    ,a.vat_amount
    ,a.contract_id
    ,a.asset_id
    ,a.charge_name AS charge_description
FROM
(
SELECT 
    C.sequence_number
    ,C.bk_aggregated_dim_contract_id AS contract_id
    ,RC.name AS charge_name
    ,SRPD.asset_id
    ,SUM(SRPD.amount_amount) AS sundry_charge_amount
    ,SUM(SRPD.vat_amount_amount) AS vat_amount
 
FROM aggregated_odessa_dim_sundry_recurring SR
JOIN aggregated_odessa_dim_sundry_recurring_payment_detail AS SRPD ON SR.bk_aggregated_dim_sundry_recurring_id = SRPD.sundry_recurring_id AND SRPD.current_flag = 1
JOIN aggregated_odessa_dim_contract C ON SR.contract_id = C.bk_aggregated_dim_contract_id AND C.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receivable_code RC ON SR.receivable_code_id = RC.bk_aggregated_dim_receivable_code_id AND RC.current_flag = 1
WHERE SRPD.current_flag = 1
    AND SR.current_flag = 1
    AND C.current_flag = 1
    AND RC.current_flag = 1
    AND SR.is_asset_based = 1
GROUP BY C.sequence_number ,C.bk_aggregated_dim_contract_id, SRPD.asset_id, RC.name
) AS a

;
GO
-- ----------------------------------------------------------
-- View: vw_asset_additional_charges
-- Depends on: vw_additional_charges_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_additional_charges
AS
SELECT      
			SUM([charges]) AS charges,
			SUM([vat_amount]) AS vat_amount,
			[sequence_number],
			[contract_id],
			[asset_id]
FROM vw_additional_charges_detail
GROUP BY 
			[contract_id],
			[sequence_number],
			[asset_id]

;
GO
-- ----------------------------------------------------------
-- View: vw_asset_description
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_description AS
-- equipment description to use when grouping assets 
WITH tidy_up AS (
SELECT  DISTINCT
asset.bk_aggregated_dim_asset_id as asset_id,
asset.manufacturer_name,
CASE WHEN COALESCE(asset.make_name, '') = 'Other' THEN '' ELSE asset.make_name END AS make_name_for_asset_description,
CASE WHEN COALESCE(asset.model_name, '') = 'Other' THEN '' ELSE asset.model_name END AS model_name_for_asset_description,
CASE WHEN axleconfig.value IS NULL THEN '' END AS axle_config_for_asset_description,
bodytype.body_type_code AS body_type,
CASE WHEN COALESCE(bodytype.body_type_code, '') LIKE '%Bus%' and asset.product_name LIKE '%Bus%' THEN '' ELSE asset.product_name END AS vehicle_category_for_asset_description,
asset.product_name

FROM aggregated_odessa_dim_asset asset
JOIN aggregated_odessa_fact_asset_status fstatus ON fstatus.sk_aggregated_dim_asset = asset.sk_aggregated_dim_asset 
JOIN aggregated_odessa_dim_asset_vehicle_additional_details AS addDetails ON addDetails.sk_aggregated_dim_asset_vehicle_additional_details= fstatus.sk_aggregated_dim_asset_vehicle_additional_details AND addDetails.current_flag = 1
JOIN aggregated_odessa_dim_asset_status dstatus ON dstatus.sk_aggregated_dim_asset_status = fstatus.sk_aggregated_dim_asset_status 
JOIN aggregated_odessa_dim_asset_type type ON type.sk_aggregated_dim_asset_type = fstatus.sk_aggregated_dim_asset_type AND type.current_flag = 1
JOIN aggregated_odessa_dim_vehicle_detail detail ON detail.[sk_aggregated_dim_vehicle_detail] = fstatus.sk_aggregated_dim_vehicle_detail AND detail.current_flag = 1
LEFT JOIN aggregated_odessa_dim_asset_vehicle_add_details_configs AS axleconfig ON  axleconfig.bk_aggregated_dim_asset_vehicle_add_details_configs_id = addDetails.[axle_config_id] AND axleconfig.current_flag = 1
LEFT JOIN aggregated_odessa_dim_body_type_config AS bodytype ON detail.body_type_config_id = bodytype.[bk_aggregated_dim_body_type_config_id] AND bodytype.current_flag = 1

WHERE asset.current_flag = 1
) , manufacturer_and_make AS (
SELECT 
asset_id, 
CASE WHEN make_name_for_asset_description IS NOT NULL 
AND make_name_for_asset_description != ''
AND manufacturer_name != make_name_for_asset_description
 THEN CONCAT([manufacturer_name], ' ', [make_name_for_asset_description]) ELSE manufacturer_name END AS manufacturer_and_make,
 manufacturer_name,
model_name_for_asset_description,
axle_config_for_asset_description,
body_type,
vehicle_category_for_asset_description
FROM tidy_up
), manufacturer_make_and_model AS (
SELECT 
asset_id, 
CASE WHEN model_name_for_asset_description IS NOT NULL 
AND model_name_for_asset_description != '' 
THEN  CONCAT(manufacturer_and_make, ' ', model_name_for_asset_description) ELSE manufacturer_and_make END AS manufacturer_make_and_model,
axle_config_for_asset_description,
body_type,
vehicle_category_for_asset_description
FROM manufacturer_and_make
), manufacturer_make_model_and_axl AS (
SELECT
asset_id, 
CASE WHEN axle_config_for_asset_description IS NOT NULL 
AND axle_config_for_asset_description != ''
THEN  CONCAT(manufacturer_make_and_model, ' ', axle_config_for_asset_description) ELSE manufacturer_make_and_model END AS manufacturer_make_model_and_axl,
body_type,
vehicle_category_for_asset_description
FROM manufacturer_make_and_model
), manufacturer_make_model_body_and_axl AS (
SELECT 
asset_id, 
CASE WHEN body_type IS NOT NULL  
AND body_type != '' 
THEN CONCAT(manufacturer_make_model_and_axl, ' ', body_type) ELSE manufacturer_make_model_and_axl END AS manufacturer_make_model_body_and_axl,
vehicle_category_for_asset_description
FROM manufacturer_make_model_and_axl
)
SELECT 
asset_id,
CASE WHEN vehicle_category_for_asset_description IS NOT NULL  
AND vehicle_category_for_asset_description != ''
THEN CONCAT(manufacturer_make_model_body_and_axl, ' ', vehicle_category_for_asset_description) ELSE manufacturer_make_model_body_and_axl END AS asset_description
FROM manufacturer_make_model_body_and_axl

;
GO
-- ----------------------------------------------------------
-- View: vw_asset_features
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_features
AS 
SELECT * 
FROM
(
    SELECT
        features.asset_id,	
        features.alias AS feature_reg_num,
        features.[equipment_id],
        reg.asset_registration_effective_date,
		reg.registration_number as vehicle_reg_num,          
        category.name AS feature_vehicle_category,
        features.[send_to_r_two_c],
        features.[r_two_c_create_time],
        features.[r_two_c_last_update_status],
        features.[r_two_c_failure_reason],
        features.[r_two_c_create_status],
        ROW_NUMBER() OVER(PARTITION BY features.equipment_id ORDER BY reg.asset_registration_effective_date DESC) AS cleanse_reg
    FROM aggregated_odessa_dim_asset_features AS features 
    LEFT JOIN aggregated_odessa_dim_asset_categories AS category ON features.asset_category_id = category.[bk_aggregated_dim_asset_categories_id] AND category.current_flag = 1
    LEFT JOIN aggregated_odessa_dim_asset_registration_detail AS reg ON reg.asset_id = features.asset_id AND reg.current_flag = 1 
    WHERE features.current_flag = 1
) AS a
WHERE a.cleanse_reg = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_contract_assignments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_contract_assignments
AS 
SELECT *
FROM
(
    SELECT 
        eContract.contract_id
        ,Users.full_name AS employee_name
        ,rFunction.name AS role_function
        ,rFunction.[system_defined_name]
        ,ROW_NUMBER() OVER(PARTITION BY eContract.contract_id ORDER BY eContract.is_primary DESC) AS primary_contact
    FROM aggregated_odessa_dim_employees_assigned_to_contract AS eContract
        JOIN aggregated_odessa_dim_employees_assigned_to_party AS eParty ON eContract.[employee_assigned_to_party_id] = eParty.[bk_aggregated_dim_employees_assigned_to_party_id]
        JOIN aggregated_odessa_dim_role_function AS rFunction ON eParty.[role_function_id] = rFunction.[bk_aggregated_dim_role_function_id] 
        JOIN aggregated_odessa_dim_user AS Users ON eParty.[employee_id] = Users.[bk_aggregated_dim_user_id]
    WHERE eContract.current_flag = 1
        AND eParty.current_flag = 1
        AND rFunction.current_flag = 1
        AND Users.current_flag = 1
) AS a
WHERE a.primary_contact = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_customer_assignments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_customer_assignments
AS 

With customer AS (
SELECT bk_aggregated_dim_customer_id, party_name FROM aggregated_odessa_dim_customer
WHERE current_flag = 1 AND status = 'Active'
), sales_rep as (
SELECT DISTINCT
EmployeeAssigned.employee_id,
EmployeeAssigned.party_id AS customer_id,
DimUser.full_name AS employee_name,
RoleFunction.name AS role_function,
RoleFunction.system_defined_name

FROM aggregated_odessa_dim_employees_assigned_to_party AS EmployeeAssigned
JOIN aggregated_odessa_dim_role_function AS RoleFunction ON EmployeeAssigned.[role_function_id] = RoleFunction.[bk_aggregated_dim_role_function_id] AND RoleFunction.current_flag = 1 AND RoleFunction.name = 'Sales Rep'
JOIN aggregated_odessa_dim_user AS DimUser ON EmployeeAssigned.employee_id = DimUser.[bk_aggregated_dim_user_id] AND DimUser.current_flag = 1

WHERE EmployeeAssigned.current_flag = 1 AND EmployeeAssigned.is_primary = 1  AND EmployeeAssigned.is_active = 1
), account_manager AS (
SELECT DISTINCT
EmployeeAssigned.employee_id,
EmployeeAssigned.party_id AS customer_id,
DimUser.full_name AS employee_name,
RoleFunction.name AS role_function,
RoleFunction.system_defined_name

FROM aggregated_odessa_dim_employees_assigned_to_party AS EmployeeAssigned
JOIN aggregated_odessa_dim_role_function AS RoleFunction ON EmployeeAssigned.[role_function_id] = RoleFunction.[bk_aggregated_dim_role_function_id] AND RoleFunction.current_flag = 1 AND RoleFunction.name = 'Account Manager'
JOIN aggregated_odessa_dim_user AS DimUser ON EmployeeAssigned.employee_id = DimUser.[bk_aggregated_dim_user_id] AND DimUser.current_flag = 1

WHERE EmployeeAssigned.current_flag = 1 AND EmployeeAssigned.is_primary = 1  AND EmployeeAssigned.is_active = 1
)

SELECT 
bk_aggregated_dim_customer_id AS customer_id,
party_name,
COALESCE(sr.employee_name, ac.employee_name) AS employee_name,
COALESCE(sr.role_function, ac.role_function) AS role_function,
COALESCE(sr.system_defined_name, ac.system_defined_name) AS system_defined_name
FROM customer AS c
LEFT JOIN sales_rep AS sr on c.bk_aggregated_dim_customer_id = sr.customer_id
LEFT JOIN account_manager AS ac ON c.bk_aggregated_dim_customer_id = ac.customer_id

;
GO
-- ----------------------------------------------------------
-- View: vw_credit_application
-- Depends on: vw_customer_assignments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_credit_application
AS 
SELECT *
FROM
(
SELECT 
		cProfile.master_lease_agreement
		,cProfile.line_type
		,cProfile.aag_contract_type

		,cProfile.pre_approval_loc_id
		,cProfile.line_of_credit_id
		,opportunity.bk_aggregated_dim_opportunity_id AS opportunity_id
		,opportunity.customer_id
		,cProfile.bk_aggregated_dim_credit_profile_id AS credit_profile_id
		,opportunity.number AS application_id
		,opportunity.number AS opportunity_number			
		,cProfile.number AS credit_profile_number	

		,opportunity.report_status 
		,cProfile.status AS loc_status
		,cProfile.status
		,application.status AS application_status		
		,cProfile.status_date

		,cProfile.requested_amount_amount
		,cProfile.approved_amount_amount
		,cProfile.used_amount_amount

		,opportunityUser.full_name AS application_owner
		,customer.[company_name]
		,customer.[sales_force_customer_name]
        ,crStructure.bk_aggregated_dim_credit_approved_structure_id AS credit_approved_structure_id
		,crStructure.expected_commencement_date
		,crStructure.[deal_product_type_id]
		,crStructure.customer_term
		,crStructure.payment_frequency
		,crStructure.amount_amount
		,crStructure.number_of_inception_payments
		,crStructure.estimated_balloon_amount_amount
		,crStructure.[rent_amount]
		,center.[description] AS cost_centre
		,cProfile.created_time
		,cProfile.updated_time
		,cProfile.[master_lease_agreement] AS 'AAG Contract Number'    
		,cProfile.[notice_period]   
		,cProfile.[is_all_assets_taken_down]
		,cProfile.[is_pre_approved]
		,cProfile.[is_pre_approval]
		,application.[submitted_to_credit_date]  
		,application.created_time AS application_created_date

		,productType.[transaction_type]

		,opportunityUser.full_name AS opportunity_owner  
		,assignedUser.full_name AS assigned_user
		,applicationUser.full_name AS application_created_by 
		,updateUser.full_name AS updated_by	
		,salesRep.[employee_name] AS primary_sales_rep   
		,creditUser.full_name AS loc_created_by 	

		,lEntity.[legal_entity_number]
		,lEntity.[name] AS legal_entity
		,branch.[branch_name]
		,lBusiness.[name] AS line_of_business
		,ISNULL(asset.equipment_count,0) AS equipment_count				

FROM aggregated_odessa_dim_opportunity AS opportunity 
LEFT JOIN  aggregated_odessa_dim_credit_profile AS cProfile ON opportunity.bk_aggregated_dim_opportunity_id = cProfile.opportunity_id AND cProfile.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_customer AS customer ON customer.bk_aggregated_dim_customer_id = opportunity.customer_id AND customer.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_credit_approved_structure AS crStructure ON crStructure.credit_profile_id = cProfile.bk_aggregated_dim_credit_profile_id AND crStructure.current_flag = 1 AND crStructure.number = 1
LEFT JOIN  aggregated_odessa_dim_cost_center AS center ON center.[bk_aggregated_dim_cost_center_id] = opportunity.[cost_center_id] AND center.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_user opportunityUser ON opportunity.created_by_id = opportunityUser.[bk_aggregated_dim_user_id] AND opportunityUser.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_user AS assignedUser ON cProfile.[assigned_to_user_id] = assignedUser.[bk_aggregated_dim_user_id] AND assignedUser.current_flag = 1  
LEFT JOIN  aggregated_odessa_dim_user AS updateUser ON cProfile.[updated_by_id] = updateUser.[bk_aggregated_dim_user_id] AND updateUser.current_flag = 1 

LEFT JOIN  aggregated_odessa_dim_deal_product_type AS productType ON productType.[bk_aggregated_dim_deal_product_type_id] = crStructure.[deal_product_type_id] AND productType.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_legal_entity AS lEntity ON lEntity.[bk_aggregated_dim_legal_entity_id] = opportunity.[legal_entity_id] AND lEntity.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_branch AS branch ON opportunity.branch_id = branch.[bk_aggregated_dim_branch_id] AND branch.current_flag = 1 
LEFT JOIN  aggregated_odessa_dim_line_of_business AS lBusiness ON opportunity.[lineof_business_id] = lBusiness.[bk_aggregated_dim_line_of_business_id] AND lBusiness.current_flag = 1
LEFT JOIN  
		(
			SELECT credit_application_id
				   ,COUNT(asset_id) AS equipment_count
			FROM aggregated_odessa_dim_credit_application_asset AS asset
			WHERE asset.current_flag = 1        
			GROUP BY credit_application_id
		) AS asset
		ON asset.[credit_application_id] = cProfile.[opportunity_id]
LEFT JOIN aggregated_odessa_dim_credit_application AS application ON application.[bk_aggregated_dim_credit_application_id] = opportunity.bk_aggregated_dim_opportunity_id AND application.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_user AS applicationUser ON application.[created_by_id] = applicationUser.[bk_aggregated_dim_user_id] AND applicationUser.current_flag = 1
LEFT JOIN  aggregated_odessa_dim_user AS creditUser ON cProfile.[created_by_id] = creditUser.[bk_aggregated_dim_user_id] AND creditUser.current_flag = 1
LEFT JOIN vw_customer_assignments AS salesRep ON salesRep.customer_id = customer.bk_aggregated_dim_customer_id AND salesRep.system_defined_name = 'SalesRep'
WHERE opportunity.current_flag = 1
) AS a

;
GO
-- ----------------------------------------------------------
-- View: vw_in_application
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_in_application AS

WITH app_asset AS (
SELECT 
ca.bk_aggregated_dim_credit_application_id,
cu.party_name,
ca.status,
o.number AS opp_number,
o.report_status,
cc.description AS cost_center,
caa.asset_id,
ca.created_by_id,
applicationUser.full_name AS app_created_by 


FROM aggregated_odessa_dim_credit_application AS ca 
JOIN aggregated_odessa_dim_opportunity AS o ON o.[bk_aggregated_dim_opportunity_id] = ca.[bk_aggregated_dim_credit_application_id] AND o.current_flag = 1
JOIN aggregated_odessa_dim_credit_application_asset AS caa ON ca.bk_aggregated_dim_credit_application_id = caa.[credit_application_id] AND caa.current_flag = 1
JOIN aggregated_odessa_dim_customer AS cu ON o.customer_id = cu.[bk_aggregated_dim_customer_id] AND cu.current_flag = 1
JOIN aggregated_odessa_dim_cost_center AS cc ON o.[cost_center_id] = cc.[bk_aggregated_dim_cost_center_id] AND cc.current_flag = 1
LEFT JOIN aggregated_odessa_dim_credit_profile AS cp ON ca.[bk_aggregated_dim_credit_application_id] = cp.opportunity_id AND cp.current_flag = 1
LEFT JOIN aggregated_odessa_dim_user AS applicationUser ON ca.[created_by_id] = applicationUser.[bk_aggregated_dim_user_id] AND applicationUser.current_flag = 1

WHERE ca.current_flag = 1
AND ca.status IN ('Pending', 'SubmittedToCredit')
AND cp.bk_aggregated_dim_credit_profile_id IS NULL
),
app_asset_structure AS (
SELECT 
ca.bk_aggregated_dim_credit_application_id,
o.customer_id,
cu.party_name,
ca.status,
o.number AS opp_number,
o.report_status,
cas.number AS exhibit_number, 
capr.expected_disbursement_date,
casa.asset_id,
cp.[bk_aggregated_dim_credit_profile_id],
dt.product_type,
tt.transaction_type

FROM aggregated_odessa_dim_credit_application AS ca 
JOIN aggregated_odessa_dim_opportunity AS o ON o.[bk_aggregated_dim_opportunity_id] = ca.[bk_aggregated_dim_credit_application_id] AND o.current_flag = 1
JOIN aggregated_odessa_dim_credit_application_structure AS cas ON ca.bk_aggregated_dim_credit_application_id = cas.credit_application_id AND cas.current_flag = 1  AND cas.is_active = 1
JOIN aggregated_odessa_dim_credit_application_structure_asset AS casa ON cas.[bk_aggregated_dim_credit_application_structure_id] = casa.[credit_application_structure_id] and casa.current_flag = 1 AND casa.is_active = 1
JOIN aggregated_odessa_dim_credit_application_pricing_detail AS capr ON cas.[bk_aggregated_dim_credit_application_structure_id]  = capr.[bk_aggregated_dim_credit_application_pricing_detail_id] AND capr.current_flag = 1 AND capr.is_active = 1
JOIN aggregated_odessa_dim_customer AS cu ON o.customer_id = cu.[bk_aggregated_dim_customer_id] AND cu.current_flag = 1
JOIN aggregated_odessa_dim_deal_type AS dt ON cas.[deal_type_id] = dt.[bk_aggregated_dim_deal_type_id] AND dt.current_flag = 1
JOIN aggregated_odessa_dim_deal_product_type AS tt ON cas.[transaction_type_id] = tt.[bk_aggregated_dim_deal_product_type_id] AND tt.current_flag = 1
LEFT JOIN aggregated_odessa_dim_credit_profile AS cp ON ca.[bk_aggregated_dim_credit_application_id] = cp.opportunity_id AND cp.current_flag = 1
WHERE ca.current_flag = 1
AND ca.status IN ('Pending', 'SubmittedToCredit')
AND cp.bk_aggregated_dim_credit_profile_id IS NULL
),
credit_profile AS (
SELECT 
cp.[bk_aggregated_dim_credit_profile_id],
cu.party_name,
cp.number AS credit_number,
o.number AS opp_number,
cc.description AS cost_center,
--cp.opportunity_id,
cp.status,
cp.report_status,
--cp.master_lease_agreement,
cas.number,
cas.expected_commencement_date,
cpasa.asset_id,
contract.sequence_number,
contract.status AS booking_status,
dt.product_type,
dpt.transaction_type,
applicationUser.full_name AS opp_created_by,
ROW_NUMBER() OVER( PARTITION BY cpasa.asset_id, cp.number ORDER BY cas.number DESC) AS child_app
FROM aggregated_odessa_dim_credit_profile as cp
JOIN aggregated_odessa_dim_opportunity AS o ON o.[bk_aggregated_dim_opportunity_id] = cp.[opportunity_id] AND o.current_flag = 1
JOIN aggregated_odessa_dim_credit_approved_structure AS cas ON cp.[bk_aggregated_dim_credit_profile_id] = cas.credit_profile_id AND cas.current_flag = 1 AND cas.is_active = 1
JOIN aggregated_odessa_dim_credit_profile_approved_structure_asset AS cpasa ON cas.[bk_aggregated_dim_credit_approved_structure_id] = cpasa.[credit_approved_structure_id] AND cpasa.current_flag = 1 AND cpasa.is_active = 1
JOIN aggregated_odessa_dim_customer AS cu ON o.customer_id = cu.[bk_aggregated_dim_customer_id] AND cu.current_flag = 1
JOIN aggregated_odessa_dim_deal_type AS dt ON cas.[deal_type_id] = dt.[bk_aggregated_dim_deal_type_id] AND dt.current_flag = 1
JOIN aggregated_odessa_dim_deal_product_type AS dpt ON cas.[deal_product_type_id] = dpt.[bk_aggregated_dim_deal_product_type_id] AND dpt.current_flag = 1
JOIN aggregated_odessa_dim_cost_center AS cc ON cp.[cost_center_id] = cc.[bk_aggregated_dim_cost_center_id] AND cc.current_flag = 1
LEFT JOIN aggregated_odessa_dim_contract AS contract ON cas.[bk_aggregated_dim_credit_approved_structure_id]= contract.[credit_approved_structure_id] AND contract.current_flag = 1 AND contract.status != 'Inactive'
LEFT JOIN aggregated_odessa_dim_user AS applicationUser ON o.[created_by_id] = applicationUser.[bk_aggregated_dim_user_id] AND applicationUser.current_flag = 1

WHERE cp.current_flag = 1
AND cp.status NOT IN ('Inactivate', 'Declined', 'OpportunityWithdrawn', 'Cancelled')
),
in_app AS (
SELECT asset.bk_aggregated_dim_asset_id, asset.alias, 
--CASE WHEN (app_asset_structure.status IS NULL AND credit_profile.credit_number IS NULL AND app_asset.status IS NULL) THEN 0 ELSE 1 END AS in_application,
CASE
WHEN credit_profile.sequence_number IS NOT NULL AND credit_profile.booking_status = 'InstallingAssets'  THEN 'contract installing assets'
WHEN credit_profile.sequence_number IS NOT NULL AND credit_profile.booking_status = 'Pending'  THEN 'contract pending'
WHEN credit_profile.sequence_number IS NOT NULL AND credit_profile.booking_status <> 'Pending'THEN 'converted to contract'
    WHEN credit_profile.sequence_number is null and credit_profile.credit_number IS NOT NULL THEN 'line of credit'
        WHEN (credit_profile.credit_number IS NULL AND app_asset_structure.status IS NOT NULL) THEN 'app structure'
        WHEN (credit_profile.credit_number IS NULL AND app_asset_structure.status IS NULL and app_asset.bk_aggregated_dim_credit_application_id IS NOT NULL) THEN 'app'
    ELSE 'not in application'
END AS stage,

--APP ASSET
app_asset.bk_aggregated_dim_credit_application_id,
app_asset.party_name AS app_company_name,
app_asset.opp_number AS app_opp_number,
app_asset.cost_center AS app_cost_center,
app_asset.app_created_by,
app_asset.status AS app_status,


--APP ASSET STRUCTURE
app_asset_structure.party_name AS app_structure_company_name,
app_asset_structure.opp_number AS app_structure_opp_number,
app_asset_structure.exhibit_number, 
app_asset_structure.expected_disbursement_date,
app_asset_structure.product_type AS app_structure_product_type,
app_asset_structure.transaction_type AS app_structure_transaction_type,


--CREDIT PROFILE
credit_profile.[bk_aggregated_dim_credit_profile_id],
credit_profile.party_name AS loc_company_name,
credit_profile.credit_number,
credit_profile.opp_number AS loc_opp_number,
credit_profile.cost_center AS loc_cost_center,
credit_profile.status AS loc_status,
credit_profile.number,
credit_profile.child_app,
credit_profile.expected_commencement_date,
credit_profile.sequence_number,
credit_profile.booking_status,
credit_profile.product_type,
credit_profile.transaction_type,
credit_profile.opp_created_by,
COALESCE(credit_profile.transaction_type, app_asset_structure.transaction_type) AS combined_product_name,
COALESCE(credit_profile.party_name, app_asset.party_name) as combined_company_name,
COALESCE(credit_profile.opp_number, app_asset_structure.opp_number, app_asset.opp_number) AS combined_opp_number,
COALESCE(app_asset.app_created_by, credit_profile.opp_created_by) AS combined_created_by


FROM aggregated_odessa_dim_asset as asset
LEFT JOIN app_asset ON asset.bk_aggregated_dim_asset_id = app_asset.asset_id
LEFT JOIN app_asset_structure ON asset.bk_aggregated_dim_asset_id = app_asset_structure.asset_id 
LEFT JOIN credit_profile ON asset.bk_aggregated_dim_asset_id = credit_profile.asset_id AND credit_profile.child_app = 1 
WHERE asset.current_flag = 1
)
SELECT * FROM in_app 
WHERE stage NOT IN ('converted to contract', 'not in application')

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_additional_charges
-- Depends on: vw_additional_charges_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_additional_charges
AS
SELECT      
		SUM([charges]) AS charges,
		SUM([vat_amount]) AS vat_amount,
		[contract_id],
		[sequence_number]		
FROM vw_additional_charges_detail AS chgDetail
GROUP BY 
		[sequence_number],
		[contract_id]

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_asset_all
-- Depends on: vw_asset_additional_charges
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_asset_all
AS
SELECT DISTINCT
asset.nbv_amount,
asset.customer_cost_amount,
asset.specific_cost_adjustment_amount,
asset.rent_amount,
asset.accumulated_depreciation_amount,
asset.fmv_amount,
asset.initial_customer_cost_amount,
asset.initial_nbv_amount,
asset.capitalized_additional_charge_amount,
asset.sk_aggregated_dim_customer,
asset.sk_aggregated_dim_date_value_as_of_date,
asset.sk_aggregated_dim_date_termination_date,	
asset.booked_residual_amount,
asset.rv_recap_amount_amount,
asset.bk_aggregated_dim_asset_id AS asset_id,
asset.bk_aggregated_dim_asset_id,
asset.is_eligible_for_billing,
asset.is_approved,
asset.bk_aggregated_dim_contract_id AS contract_id,
asset.sequence_number,
asset.status,
asset.bk_aggregated_dim_customer_id AS customer_id,
td.[bk_aggregated_dim_date] as termination_date,
ISNULL(charges.charges,0) AS asset_budget_value,
ISNULL(charges.charges,0) + ISNULL(asset.rent_amount,0) AS total_charge_to_customer
FROM (
SELECT 
con.bk_aggregated_dim_contract_id,
con.sequence_number,
con.status,
cu.bk_aggregated_dim_customer_id,
a.bk_aggregated_dim_asset_id,
ROW_NUMBER() OVER(PARTITION BY con.bk_aggregated_dim_contract_id, a.bk_aggregated_dim_asset_id ORDER BY fla.sk_aggregated_dim_date_record DESC, fla.sk_aggregated_dim_time_record DESC) AS rn,
fla.sk_aggregated_dim_date_termination_date,
fla.nbv_amount,
fla.customer_cost_amount,
fla.specific_cost_adjustment_amount,
fla.rent_amount,
fla.accumulated_depreciation_amount,
fla.fmv_amount,
fla.initial_customer_cost_amount,
fla.initial_nbv_amount,
fla.capitalized_additional_charge_amount,
fla.sk_aggregated_dim_customer,
fla.sk_aggregated_dim_date_value_as_of_date,
fla.booked_residual_amount,
fla.rv_recap_amount_amount,
dla.is_eligible_for_billing,
dla.is_approved

FROM aggregated_odessa_dim_contract AS con
JOIN aggregated_odessa_fact_lease_asset AS fla ON con.sk_aggregated_dim_contract = fla.sk_aggregated_dim_contract
JOIN aggregated_odessa_dim_lease_asset AS dla ON fla.sk_aggregated_dim_lease_asset = dla.sk_aggregated_dim_lease_asset and dla.is_approved = 1
JOIN aggregated_odessa_dim_asset AS a ON fla.sk_aggregated_dim_asset = a.sk_aggregated_dim_asset
LEFT JOIN aggregated_odessa_dim_vehicle_detail AS vd ON a.bk_aggregated_dim_asset_id = vd.bk_aggregated_dim_vehicle_detail_id
JOIN aggregated_odessa_dim_lease_finance AS lf ON fla.sk_aggregated_dim_lease_finance = lf.sk_aggregated_dim_lease_finance AND lf.is_current = 1
JOIN aggregated_odessa_dim_customer AS cu ON fla.sk_aggregated_dim_customer = cu.sk_aggregated_dim_customer
LEFT JOIN aggregated_odessa_dim_branch AS b ON fla.[sk_aggregated_dim_branch] = b.sk_aggregated_dim_branch
LEFT JOIN (select *, row_number() over (partition by asset_id order by asset_registration_effective_date desc) RegRN from aggregated_odessa_dim_asset_registration_detail where current_flag = 1) AS reg 
        ON reg.asset_id = a.bk_aggregated_dim_asset_id AND reg.current_flag = 1 AND RegRN=1
        WHERE con.current_flag = 1
    ) AS asset
LEFT JOIN aggregated_odessa_dim_date as td ON asset.sk_aggregated_dim_date_termination_date = td.sk_aggregated_dim_date 
LEFT JOIN vw_asset_additional_charges AS charges ON charges.contract_id = asset.bk_aggregated_dim_contract_id AND charges.asset_id = asset.bk_aggregated_dim_asset_id       

WHERE asset.rn = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_asset_current
-- Depends on: vw_lease_asset_all
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_asset_current
AS
SELECT *
FROM vw_lease_asset_all 
WHERE termination_date = '9999-01-01'
AND status <> 'Inactive' 

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_finance_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_finance_detail
AS
SELECT    *
FROM
(
	SELECT  
					fDetail.booked_residual_amount,
					fDetail.regular_payment_amount_amount,
					fDetail.total_down_payment_amount,
					fDetail.bank_yield_spread,
					fDetail.total_yield,
					fDetail.rent_amount,
					fDetail.net_investment_amount,
					IRdetail.base_rate,
					IRdetail.spread,
					IRdetail.interest_rate,	
					fDetail.total_upfront_tax_amount_amount,
					fDetail.true_down_payment_amount,
					fDetail.vat_down_payment_amount,
					fDetail.number_of_payments,
					fDetail.maturity_payment_amount,
					fDetail.down_payment_amount,
					fDetail.florida_stamp_tax_amount,
					fDetail.fmv_amount,
					fDetail.inception_payment_amount,
					fDetail.interim_rent_amount,
					dFinance.tax_deferral_numberof_payments,
					dFinance.tax_deferral_payment_number,
					dFinance.is_over_term_lease,										
					fDetail.cost_of_funds,
					fDetail.deferred_tax_balance_amount,
					fDetail.capitalized_sales_tax_down_payment_amount,
					fDetail.calculated_tax_deferral_amount_amount,
					fDetail.sk_aggregated_dim_date_maturity_date,
					fDetail.sk_aggregated_dim_date_commencement_date,
					fDetail.sk_aggregated_dim_line_of_business,
					fDetail.sk_aggregated_dim_legal_entity,
					fDetail.sk_aggregated_dim_customer,
					fDetail.sk_aggregated_dim_cost_center,
					fDetail.sk_aggregated_dim_date_post_date,
					fDetail.sk_aggregated_dim_date_record,
					fDetail.sk_aggregated_dim_time_record,
					ROW_NUMBER() OVER(PARTITION BY contract.bk_aggregated_dim_contract_id ORDER BY fDetail.sk_aggregated_dim_contract DESC, fDetail.sk_aggregated_dim_customer DESC, leaseIR.sk_aggregated_dim_lease_interest_rate DESC, fDetail.sk_aggregated_dim_date_record DESC, fDetail.sk_aggregated_dim_time_record DESC) AS current_contract_detail,		
					ROW_NUMBER() OVER(PARTITION BY fDetail.sk_aggregated_dim_lease_finance ORDER BY fDetail.sk_aggregated_dim_contract DESC, fDetail.sk_aggregated_dim_customer DESC, leaseIR.sk_aggregated_dim_lease_interest_rate DESC, fDetail.sk_aggregated_dim_date_record DESC, fDetail.sk_aggregated_dim_time_record DESC) AS current_lease_detail,
					fDetail.sk_aggregated_dim_contract AS sk_current_fact_contract,
                    contract.sk_aggregated_dim_contract AS sk_current_dim_contract,

					fDetail.sk_aggregated_dim_customer AS sk_current_fact_customer,
                    customerCurrent.sk_aggregated_dim_customer AS sk_current_dim_customer,
					dFinance.sk_aggregated_dim_lease_finance AS sk_current_dim_lease_finance,

                    fDetail.sk_aggregated_dim_contract,
					fDetail.sk_aggregated_dim_branch,
					fDetail.sk_aggregated_dim_lease_finance,
                    contract.bk_aggregated_dim_contract_id AS contract_id ,
                    contract.sequence_number,
                    leaseIR.interest_rate_detail_id,
                    IRdetail.bk_aggregated_dim_interest_rate_detail_id		                 

	FROM aggregated_odessa_fact_lease_finance_detail AS fDetail
    JOIN aggregated_odessa_dim_lease_finance AS dFinance ON dFinance.sk_aggregated_dim_lease_finance = fDetail.sk_aggregated_dim_lease_finance AND dFinance.is_current = 1 AND dFinance.current_flag = 1
    LEFT JOIN aggregated_odessa_dim_lease_interest_rate AS leaseIR ON leaseIR.lease_finance_detail_id = dFinance.bk_aggregated_dim_lease_finance_id AND leaseIR.current_flag = 1
	LEFT JOIN aggregated_odessa_dim_interest_rate_detail AS IRdetail ON IRdetail.bk_aggregated_dim_interest_rate_detail_id = leaseIR.interest_rate_detail_id AND IRdetail.is_active = 1 AND IRdetail.current_flag = 1 
    JOIN aggregated_odessa_dim_contract AS contract ON contract.sk_aggregated_dim_contract = fDetail.sk_aggregated_dim_contract AND contract.current_flag = 1
    JOIN aggregated_odessa_dim_customer AS customer ON customer.sk_aggregated_dim_customer = fDetail.sk_aggregated_dim_customer 
    LEFT JOIN aggregated_odessa_dim_customer AS customerCurrent ON customerCurrent.bk_aggregated_dim_customer_id = customer.bk_aggregated_dim_customer_id AND customerCurrent.current_flag = 1    
	JOIN aggregated_odessa_dim_branch AS branch ON branch.sk_aggregated_dim_branch = fDetail.sk_aggregated_dim_branch  AND branch.current_flag = 1	
    JOIN aggregated_odessa_dim_line_of_business AS lob ON lob.sk_aggregated_dim_line_of_business = fDetail.sk_aggregated_dim_line_of_business AND lob.current_flag = 1
    JOIN aggregated_odessa_dim_cost_center AS cc ON cc.sk_aggregated_dim_cost_center = fDetail.sk_aggregated_dim_cost_center AND cc.current_flag = 1 
) AS a 
WHERE a.current_contract_detail = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_contracts
-- Depends on: vw_contract_assignments, vw_credit_application, vw_lease_asset_all, vw_lease_finance_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_contracts
AS
SELECT *
FROM
(
SELECT          
				contract.sk_aggregated_dim_contract,						
				contract.bk_aggregated_dim_contract_id AS contract_id,					
				contract.sequence_number,
				contract.external_reference_number,				
				contract.contract_type,
				contract.status,
				contract.report_status,
				contract.previous_schedule_number,
				contract.current_flag,
				contract.alias AS aag_contract_number,
				contract.grace_delinquency_days,	
				contract.created_time,
				contract.updated_time,	
				contractOrigins.start_date AS lease_start_date,				
				first_value(lFinanceDetail.sk_aggregated_dim_date_record) OVER (PARTITION BY contract.bk_aggregated_dim_contract_id ORDER BY lFinanceDetail.sk_aggregated_dim_date_record ASC , lFinanceDetail.sk_aggregated_dim_time_record ASC) AS sk_created_date,				
				CASE WHEN opportunity.number IS NULL THEN 'Yes' ELSE 'No' END AS is_migrated,

				customer.party_name AS company_name,
				customer.bk_aggregated_dim_customer_id AS customer_id,			
				customer.creation_date as customer_account_created_date,
				customer.external_reference_id,
				customer.external_reference_id AS account_number,					

				opportunity.number,
				opportunity.number AS opportunity_number,
				contractSalesRep.employee_name AS sales_rep,
				contractManager.employee_name AS account_manager,
				contractUser.full_name AS contract_created_by,				

				CASE WHEN dfinance.is_advance = 1 THEN 'Advance' ELSE 'ARREAS' END AS 'payment_method', 
				lFinanceDetail.sk_aggregated_dim_date_maturity_date AS lease_maturity_date,										
				lFinanceDetail.sk_aggregated_dim_date_commencement_date AS lease_commencement_date,

				assetleases.nbv_amount,
				assetleases.customer_cost_amount,
				assetleases.rent_amount,
				assetleases.accumulated_depreciation_amount,
				assetleases.fmv_amount,
				assetleases.initial_customer_cost_amount,
				assetleases.total_nbv_amount,
				assetleases.capitalized_additional_charge_amount,
				assetleases.asset_budget_value,
				assetleases.total_charge_to_customer,
				assetleases.number_of_assets,

				legalE.legal_entity_number,

				productType.transaction_type AS product_name,
				productType.transaction_type AS deal_type,

				classificationCode.code AS sic_code,
				classificationCode.description AS sic_desc,					

				businessType.name AS business_type,	
				cCenter.description AS cost_center,	
                lBusiness.name AS line_of_business, 	
                branch.branch_name,		

				dfinance.booking_status,
				dfinance.approval_status,
				dfinance.is_current,
				dfinance.customer_term_in_months,
				dfinance.term_in_months,		
				dfinance.remaining_lease_term_in_months,							
				dfinance.payment_frequency,
				dfinance.purchase_option,
				dfinance.classification_contract_type,
				dfinance.lease_contract_type,
				dfinance.payment_frequency_days,
				dfinance.bk_aggregated_dim_lease_finance_id AS lease_finance_id,
				dfinance.sk_aggregated_dim_lease_finance,

				lFinanceDetail.booked_residual_amount, 
				lFinanceDetail.total_yield,
				lFinanceDetail.regular_payment_amount_amount,
				lFinanceDetail.total_down_payment_amount,
				lFinanceDetail.interest_rate,
				lFinanceDetail.rent_amount AS lease_rent_amount,
				lFinanceDetail.net_investment_amount,
				lFinanceDetail.base_rate,
				lFinanceDetail.spread,
				lFinanceDetail.bank_yield_spread,
				lFinanceDetail.sk_aggregated_dim_date_post_date,
                lFinanceDetail.sk_aggregated_dim_customer,
				lFinanceDetail.capitalized_sales_tax_down_payment_amount AS tax_down_payment_amount,
				lFinanceDetail.calculated_tax_deferral_amount_amount AS tax_deferral_amount,
				lFinanceDetail.tax_deferral_numberof_payments,
				lFinanceDetail.tax_deferral_payment_number,
				lFinanceDetail.down_payment_amount,
				lFinanceDetail.inception_payment_amount,
				lFinanceDetail.is_over_term_lease,				
				crStructure.estimated_balloon_amount_amount AS balloon_payment_amount,
				ROW_NUMBER() OVER(PARTITION BY contract.bk_aggregated_dim_contract_id ORDER BY lFinanceDetail.sk_current_dim_contract DESC, lFinanceDetail.sk_current_dim_customer DESC, lFinanceDetail.sk_aggregated_dim_date_commencement_date DESC, lFinanceDetail.sk_aggregated_dim_lease_finance DESC, lFinanceDetail.sk_aggregated_dim_date_record DESC, lFinanceDetail.sk_aggregated_dim_time_record DESC) AS is_latest

FROM aggregated_odessa_dim_contract AS contract 
LEFT JOIN 
(
    SELECT  DISTINCT
                    CASE WHEN first_value(contractOrigins.start_date) OVER (PARTITION BY contractOrigins.sequence_number ORDER BY contractOrigins.start_date) = '1900-01-01 00:00:00.000000' THEN contractOrigins.dp_process_date
                        ELSE first_value(contractOrigins.start_date) OVER (PARTITION BY contractOrigins.sequence_number ORDER BY contractOrigins.start_date)
                    END AS start_date
                    ,contractOrigins.[bk_aggregated_dim_contract_id] AS contract_id
    FROM aggregated_odessa_dim_contract AS contractOrigins 
    WHERE contractOrigins.status = 'Commenced' --AND contractOrigins.report_status = 'Active'
) AS contractOrigins ON contractOrigins.contract_id = contract.bk_aggregated_dim_contract_id
LEFT JOIN 
(
SELECT 
        lease.contract_id,						
        SUM(nbv_amount) AS nbv_amount,
        SUM(customer_cost_amount) AS customer_cost_amount,
        SUM(rent_amount) AS rent_amount,
        SUM(accumulated_depreciation_amount) AS accumulated_depreciation_amount,
        SUM(fmv_amount) AS fmv_amount,
        SUM(initial_customer_cost_amount) AS initial_customer_cost_amount,
        SUM(nbv_amount) AS total_nbv_amount,
        SUM(capitalized_additional_charge_amount) AS capitalized_additional_charge_amount,
        SUM(asset_budget_value) AS asset_budget_value,
        SUM(total_charge_to_customer) AS total_charge_to_customer,
        COUNT(*) AS number_of_assets

FROM vw_lease_asset_all AS lease
WHERE lease.is_approved = 1
GROUP BY
				lease.contract_id

) AS assetleases ON contract.bk_aggregated_dim_contract_id = assetleases.contract_id 
JOIN vw_lease_finance_detail AS lFinanceDetail ON contract.sk_aggregated_dim_contract = lFinanceDetail.sk_current_dim_contract AND lFinanceDetail.current_contract_detail = 1
LEFT JOIN aggregated_odessa_dim_customer AS customer ON lFinanceDetail.sk_current_dim_customer = customer.sk_aggregated_dim_customer 
LEFT JOIN aggregated_odessa_dim_opportunity AS opportunity ON opportunity.number = contract.opportunity_number AND opportunity.current_flag = 1	
LEFT JOIN aggregated_odessa_dim_user AS contractUser ON contractUser.bk_aggregated_dim_user_id = contract.created_by_id  AND contractUser.current_flag = 1
LEFT JOIN vw_contract_assignments AS contractSalesRep ON contractSalesRep.contract_id = contract.bk_aggregated_dim_contract_id AND contractSalesRep.system_defined_name = 'SalesRep'     
LEFT JOIN vw_contract_assignments AS contractManager ON contractManager.contract_id = contract.bk_aggregated_dim_contract_id AND contractManager.system_defined_name = 'AccountManager'
LEFT JOIN aggregated_odessa_dim_deal_product_type AS productType ON productType.bk_aggregated_dim_deal_product_type_id = contract.deal_product_type_id AND productType.current_flag = 1	
LEFT JOIN aggregated_odessa_dim_cost_center AS cCenter on cCenter.bk_aggregated_dim_cost_center_id = contract.cost_center_id
LEFT JOIN aggregated_odessa_dim_legal_entity AS legalE on legalE.sk_aggregated_dim_legal_entity = lFinanceDetail.sk_aggregated_dim_legal_entity 	
LEFT JOIN aggregated_odessa_dim_line_of_business AS lBusiness ON lBusiness.sk_aggregated_dim_line_of_business = lFinanceDetail.sk_aggregated_dim_line_of_business 
LEFT JOIN aggregated_odessa_dim_date AS commencement on commencement.sk_aggregated_dim_date = lFinanceDetail.sk_aggregated_dim_date_commencement_date
LEFT JOIN aggregated_odessa_dim_business_type AS businessType ON businessType.bk_aggregated_dim_business_type_id = customer.business_type_id AND businessType.current_flag = 1	
LEFT JOIN aggregated_odessa_dim_classification_code AS classificationCode ON customer.sic_code_id = classificationCode.bk_aggregated_dim_classification_code_id AND classificationCode.current_flag = 1
LEFT JOIN aggregated_odessa_dim_branch AS branch on branch.sk_aggregated_dim_branch = lFinanceDetail.sk_aggregated_dim_branch 
LEFT JOIN aggregated_odessa_dim_lease_finance AS dfinance ON dfinance.sk_aggregated_dim_lease_finance = lFinanceDetail.sk_aggregated_dim_lease_finance 
LEFT JOIN vw_credit_application AS crStructure ON crStructure.opportunity_number = contract.opportunity_number
) AS a
WHERE a.is_latest = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_asset_in_application
-- Depends on: vw_asset, vw_credit_application, vw_lease_contracts
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_in_application
AS 
SELECT
    b.*
    , ROW_NUMBER() OVER(PARTITION BY b.asset_id ORDER BY b.application_created_date DESC) AS latest_application	

FROM
(
    SELECT a.*
    ,COALESCE(
                CASE WHEN a.lease_status IS NOT NULL THEN 'Pre-Contract' ELSE NULL END 
                , CASE WHEN a.loc_status IS NOT NULL THEN 'Line of Credit' ELSE NULL END
                , CASE WHEN a.application_status IS NOT NULL THEN 'Credit App' ELSE NULL END 
                , 'Unknown'
                   
             ) AS application_stage  
    FROM
    (
    SELECT DISTINCT
        cAppAssets.application_id AS application_id,
        cAppAssets.loc_status, ---- application_status
        cAppAssets.application_status, ---- application_stage
        cAppAssets.credit_profile_number,	
        lease.status AS lease_status,        
        cAppAssets.expected_commencement_date AS application_expected_commencement_date,	
        cAppAssets.submitted_to_credit_date,
        cAppAssets.application_created_date,	
        asset.asset_status,
        cAppAssets.transaction_type AS Lease_type,
        cAppAssets.transaction_type AS product_name,	
        cAppAssets.company_name,
        cAppAssets.legal_entity,
        cAppAssets.opportunity_number,
        cAppAssets.application_created_by AS created_by,	

        cAppAssets.asset_id,
        cAppAssets.application_id AS application_asset_id,

        asset.model_name,
        asset.make_name,
        asset.alias AS registration_number,
        asset.manufacturer_name,
        asset.aag_fleet_number,
        asset.asset_sub_type
    FROM
    (
        SELECT 
            creditApps.application_id,
            crAsset.asset_id,
            creditApps.credit_profile_number,		
            creditApps.loc_status, 
            creditApps.application_status,
            creditApps.expected_commencement_date,	
            creditApps.application_created_date,	
            creditApps.transaction_type,	
            creditApps.company_name,
            creditApps.legal_entity,
            creditApps.opportunity_number,
            creditApps.application_created_by,
            creditApps.submitted_to_credit_date			
        FROM vw_credit_application AS creditApps
        JOIN aggregated_odessa_dim_credit_profile_asset AS crAsset ON crAsset.credit_profile_id = creditApps.credit_profile_id AND crAsset.current_flag = 1	
        WHERE lOWER(creditApps.loc_status) IN ('pending','datagathering','creditanalysis','amendment','approved')   
        UNION

        SELECT 
            creditApps.application_id,
            appAsset.asset_id,
            creditApps.credit_profile_number,
            creditApps.loc_status, 
            creditApps.application_status,
            creditApps.expected_commencement_date,	
            creditApps.application_created_date,	
            creditApps.transaction_type,
            creditApps.company_name,
            creditApps.legal_entity,
            creditApps.opportunity_number,
            creditApps.application_created_by,
            creditApps.submitted_to_credit_date
        FROM vw_credit_application AS creditApps
        JOIN aggregated_odessa_dim_credit_application_asset AS appAsset ON creditApps.opportunity_id = appAsset.credit_application_id
        WHERE LOWER(creditApps.application_status) = 'pending'
        AND appAsset.current_flag = 1
    ) AS cAppAssets
    LEFT JOIN vw_asset AS asset ON cAppAssets.asset_id = asset.bk_aggregated_dim_asset_id
    LEFT JOIN vw_lease_contracts AS lease ON lease.opportunity_number = cAppAssets.opportunity_number 
    ) AS a
    
    WHERE LOWER(a.application_status) = 'pending'
    OR 
    (LOWER(a.application_status) IN ('submittedtocredit') AND LOWER(a.loc_status) IN ('pending','datagathering','creditanalysis','amendment'))
    OR
    LOWER(a.loc_status) = ('approved') AND (LOWER(a.lease_status) IN ('installingassets','pending'))
    OR
    LOWER(a.loc_status) = ('approved') AND a.lease_status IS NULL
    
) AS b

;
GO
-- ----------------------------------------------------------
-- View: vw_asset_rentals
-- Depends on: vw_asset, vw_in_application, vw_lease_asset_current, vw_lease_contracts
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_rentals
AS 
SELECT a.*, COALESCE(a.f_o_c, a.leased, a.in_application, 'No') AS [Utilised]  
FROM
(
SELECT 
    asset.asset_id
    ,contracts.company_name AS lease_company_name
    ,contracts.branch_name 
    ,contracts.[sequence_number]
	,contracts.is_migrated
    ,asset.[asset_status]
    ,asset.alias AS [registration_number]
    ,[serial_number]
    ,asset.[description]
    ,contracts.[cost_center] AS cost_centre
    ,lease.total_charge_to_customer
    ,asset.term
    ,asset_contract_type
    ,asset.[asset_sub_type]
    ,contracts.product_name AS lease_product_name
    ,asset.[make_name]
    ,asset.[model_year]
    ,asset.gvw
    ,asset.[service_intervals_vehicle]
    ,commDt.bk_aggregated_dim_date AS commenced_date
    ,contracts.lease_start_date	
    ,matDt.bk_aggregated_dim_date AS maturity_date
    ,asset.[depreciation_value]
    ,lease.rent_amount 
    ,contracts.[customer_term_in_months] AS lease_term
    ,asset.equipment_nbv   

    ,asset.oal
    ,asset.[rental_availability_status] 
    ,asset.route_into_rental_fleet
    ,asset.[body_type] 
    ,asset.[manufacturer_name]
    ,asset.city
    ,asset.legal_entity_number
    ,asset.[asset_category]
    ,asset.category_name
    ,asset.location_city 
    ,asset.[collateral_id]
    ,asset.model_name    

    ,asset.cost_basis_amount
    ,appAsset.combined_opp_number AS [application_id]
    ,appAsset.stage AS application_stage
    ,appAsset.combined_created_by AS created_by
    ,appAsset.combined_product_name AS application_product_name
    ,appAsset.loc_status
    ,appAsset.app_status AS application_status
    ,appAsset.combined_company_name AS application_company_name
    ,CASE WHEN appAsset.bk_aggregated_dim_asset_id IS NOT NULL THEN 'In Application' ELSE NULL END AS in_application    
    ,asset.body_description 
    ,asset.[vehicle_service_status] 
    ,asset.product_name AS vehicle_type
    ,asset.in_service_date 
    ,asset.[mot_passed_date]
    ,asset.[allocated_status] 
    ,asset.[reserved_by]
    ,asset.[reserved_for] 
    ,asset.[reserve_date]
    ,asset.dvsr_star_rating
    ,asset.dhl_compliant
    ,contracts.status AS lease_status
    ,CASE WHEN asset.asset_status = 'Leased' AND LOWER(contracts.status) = 'commenced' THEN 'Yes' ELSE NULL END AS leased
    --,CASE WHEN asset.asset_status <> 'Leased' THEN 'Available' ELSE NULL END AS available
    ,CASE WHEN asset.asset_status = 'Leased' AND LOWER(contracts.status) = 'commenced' AND contracts.product_name = 'Rental' AND lease.total_charge_to_customer = 0.01 THEN 'Yes (FoC)' ELSE NULL END AS f_o_c
FROM vw_asset AS asset
LEFT JOIN vw_lease_asset_current AS lease ON asset.asset_id = lease.asset_id AND lease.status IN ('Pending','Commenced','InstallingAssets')
LEFT JOIN vw_lease_contracts AS contracts ON contracts.contract_id = lease.contract_id
LEFT JOIN aggregated_odessa_dim_date AS commDt on commDt.[sk_aggregated_dim_date] = contracts.lease_commencement_date
LEFT JOIN aggregated_odessa_dim_date AS matDt on matDt.[sk_aggregated_dim_date] = contracts.lease_maturity_date
LEFT JOIN vw_in_application AS appAsset ON appAsset.bk_aggregated_dim_asset_id = asset.asset_id 
WHERE asset.[asset_contract_type] = 'Rental'
AND asset.asset_status IN ('Leased','Inventory','AwaitingDelivery')
) as a

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_payments
-- Depends on: vw_lease_finance_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_payments
AS
SELECT *
FROM
(
SELECT 
			payments.sk_aggregated_dim_lease_payment_schedule,
		    payments.payment_number,
			payments.begin_balance_amount,			
			payments.lease_finance_detail_id,
			payments.non_rental_tax_amount,
			payments.original_stub_payment_amount_amount,
			payments.pre_capitalization_payment_amount,
			payments.deferred_capitalized_sales_tax_amount,
			payments.non_rental_amount_amount,
			payments.customer_id,
			payments.vat_amount_amount,
			payments.interest_accrued_amount,
			payments.receivable_adjustment_amount_amount,
			payments.actual_payment_amount,
			payments.principal_amount,
			payments.interest_amount,
			payments.payment_structure,
			payments.amount_amount,
			payments.payment_type,
			payments.end_balance_amount,
			payments.due_date,
			payments.start_date,
			payments.end_date,
			payments.disbursement_amount,
			payments.bk_aggregated_dim_lease_payment_schedule_id AS income_stream_id,
			finance.bk_aggregated_dim_lease_finance_id,
			contractCurrent.status AS booking_status,
			finance.approval_status,
			finance.term_in_months,
			finance.total_economic_life_in_months,
			finance.total_economic_life_test_result,
			finance.compounding_frequency,
			finance.profit_loss_status,
			finance.ninety_percent_test_result_passed,
			finance.tax_deferral_start_payment_number,
			finance.remaining_economic_life_in_months,
			finance.investment_modified_after_payment,
			finance.remaining_lease_term_in_months,
			finance.payment_frequency_days,
			finance.number_of_over_term_payments,
			finance.maturity_date_basis,
			finance.lease_contract_type,
			finance.purchase_option,	
			finance.payment_frequency,
			finance.is_advance,
			finance.due_day,
			finance.aag_contract_type,
			postDt.bk_aggregated_dim_date AS post_date,
			maturityDt.bk_aggregated_dim_date AS maturity_date,	
			commDt.bk_aggregated_dim_date AS commencement_date,					
			contractCurrent.bk_aggregated_dim_contract_id AS contract_id,
			contractCurrent.sequence_number,
			contractCurrent.alias,
			contractCurrent.status,
			contractCurrent.report_status,			
			customer.company_name,
			productType.transaction_type AS deal_type,
			productType.code AS deal_type_code,
			ROW_NUMBER() OVER(PARTITION BY contractCurrent.bk_aggregated_dim_contract_id ORDER BY payments.sk_aggregated_dim_lease_payment_schedule ASC) AS schedule_number


FROM vw_lease_finance_detail AS fDetail
JOIN aggregated_odessa_dim_lease_finance AS finance ON finance.sk_aggregated_dim_lease_finance = fDetail.sk_aggregated_dim_lease_finance 
JOIN aggregated_odessa_dim_lease_payment_schedule AS payments ON payments.lease_finance_detail_id = finance.bk_aggregated_dim_lease_finance_id
JOIN aggregated_odessa_dim_date AS postDt ON postDt.sk_aggregated_dim_date = fDetail.sk_aggregated_dim_date_post_date
JOIN aggregated_odessa_dim_date AS maturityDt ON maturityDt.sk_aggregated_dim_date = fDetail.sk_aggregated_dim_date_maturity_date
JOIN aggregated_odessa_dim_contract AS contractCurrent ON contractCurrent.sk_aggregated_dim_contract = fDetail.sk_current_dim_contract
JOIN aggregated_odessa_dim_date AS commDt ON commDt.sk_aggregated_dim_date = fDetail.sk_aggregated_dim_date_commencement_date	
JOIN aggregated_odessa_dim_branch AS branch ON branch.sk_aggregated_dim_branch = fDetail.sk_aggregated_dim_branch 
JOIN aggregated_odessa_dim_line_of_business AS lob ON lob.sk_aggregated_dim_line_of_business = fDetail.sk_aggregated_dim_line_of_business 
JOIN aggregated_odessa_dim_legal_entity AS legalE ON legalE.sk_aggregated_dim_legal_entity = fDetail.sk_aggregated_dim_legal_entity 
JOIN aggregated_odessa_dim_customer AS customer ON customer.sk_aggregated_dim_customer = fDetail.sk_current_dim_customer 
JOIN aggregated_odessa_dim_cost_center AS center ON center.sk_aggregated_dim_cost_center = fDetail.sk_aggregated_dim_cost_center 
JOIN aggregated_odessa_dim_deal_product_type AS productType ON productType.bk_aggregated_dim_deal_product_type_id = contractCurrent.deal_product_type_id
WHERE payments.current_flag = 1 AND payments.is_active = 1 AND fDetail.current_contract_detail = 1
) as a

;
GO
-- ----------------------------------------------------------
-- View: vw_contract_origination
-- Depends on: vw_lease_contracts, vw_lease_payments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_contract_origination
AS
SELECT 
    contract.sequence_number
    ,contract.contract_id
    ,contract.aag_contract_number
    ,contract.opportunity_number
    ,contract.company_name
    ,contract.base_rate
    ,contract.spread
    ,contract.base_rate + contract.spread AS yield
    ,contract.total_yield
    ,contract.cost_center 
    ,contract.sales_rep
    ,contract.legal_entity_number
    ,contract.product_name
    ,contract.report_status
    ,contract.accumulated_depreciation_amount
    ,contract.external_reference_id AS account_number
    ,commDt.bk_aggregated_dim_date AS commencement_date
    ,matDT.bk_aggregated_dim_date AS maturity_date
    ,postDT.bk_aggregated_dim_date AS contract_created_date
    ,contract.term_in_months
    ,contract.total_down_payment_amount
    ,contract.total_nbv_amount
    ,contract.status
    ,contract.lease_start_date
    ,contract.asset_budget_value AS budget
    ,contract.customer_cost_amount 
    ,contract.customer_cost_amount AS asset_cost_amount
    ,contract.down_payment_amount
    ,contract.tax_deferral_amount
    ,contract.tax_deferral_payment_number
    ,contract.balloon_payment_amount
    ,contract.inception_payment_amount
    ,contract.line_of_business
    ,contract.number_of_assets
    ,contract.payment_frequency
    ,contract.is_migrated
    ,contract.nbv_amount   
    ,contract.branch_name 
    ,payments.begin_balance_amount

FROM vw_lease_contracts AS contract
LEFT JOIN aggregated_odessa_dim_date AS commDt ON commDt.sk_aggregated_dim_date = contract.lease_commencement_date
LEFT JOIN aggregated_odessa_dim_date AS matDT ON matDT.sk_aggregated_dim_date = contract.lease_maturity_date
LEFT JOIN aggregated_odessa_dim_date AS postDT ON postDT.sk_aggregated_dim_date = contract.sk_aggregated_dim_date_post_date
LEFT JOIN vw_lease_payments AS payments ON payments.contract_id = contract.contract_id AND payments.schedule_number = 1
WHERE contract.sequence_number NOT LIKE '00%'
AND LOWER(contract.status) = 'commenced'

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_payment_vat_deferrals
-- Depends on: vw_lease_payments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_payment_vat_deferrals
AS
SELECT 
taxesDeferrals.[due_date] 
,taxesDeferrals.[contract_id] 
,deferred_capitalized_sales_tax_amount
,ROW_NUMBER() OVER(PARTITION BY taxesDeferrals.contract_id ORDER BY taxesDeferrals.due_date DESC) AS latest_due_date 
FROM vw_lease_payments AS taxesDeferrals
JOIN
(
    SELECT 
        MIN(due_date) AS due_date
        ,[contract_id] 
    FROM vw_lease_payments
    GROUP BY contract_id
) AS payments ON payments.contract_id = taxesDeferrals.contract_id
WHERE deferred_capitalized_sales_tax_amount <> 0
AND taxesDeferrals.due_date <> payments.due_date

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_payments_current
-- Depends on: vw_lease_payments
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_payments_current
AS
SELECT 
         payments.*
        ,ROW_NUMBER() OVER(PARTITION BY payments.contract_id ORDER BY payments.sk_aggregated_dim_lease_payment_schedule DESC) AS latest_schedule
        ,ROW_NUMBER() OVER(PARTITION BY payments.contract_id ORDER BY payments.sk_aggregated_dim_lease_payment_schedule ASC) AS initial_schedule	
    FROM vw_lease_payments AS payments
    WHERE due_date <= GETDATE()

;
GO
-- ----------------------------------------------------------
-- View: vw_receipts
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_receipts
AS

SELECT      receipt.[bk_aggregated_dim_receipt_id],
			receipt.[number],
			receipt.[receipt_amount_amount],
			receipt.[balance_amount],
			receipt.[sk_aggregated_dim_receipt],
			receipt.[receipt_source],
			receipt.[approval_status],
			receipt.reversal_as_of_date,

			receipt.[branch_id],

			receipt.[type_id],
			receipt.[customer_id],
			receipt.[contract_id],
			receipt.[lineof_business_id],
			receipt.[instrument_type_id],

			lEntity.name AS legal_entity,
			createdBy.full_name AS created_by,
			updatedBy.full_name AS updated_by,
			receipt.[created_time],
			receipt.[check_number],
			receipt.[security_deposit_liability_amount_amount],
			receipt.[security_deposit_liability_contract_amount_amount],
	
			receipt.[post_date],
			receipt.[received_date],
			receipt.[status],
			rType.[receipt_type_name],
			bank.[automated_payment_method]
			
FROM aggregated_odessa_dim_receipt AS receipt
LEFT JOIN aggregated_odessa_dim_user AS createdBy ON receipt.created_by_id = createdBy.bk_aggregated_dim_user_id AND createdBy.current_flag = 1
LEFT JOIN aggregated_odessa_dim_user AS updatedBy ON receipt.created_by_id = updatedBy.bk_aggregated_dim_user_id AND updatedBy.current_flag = 1
LEFT JOIN aggregated_odessa_dim_legal_entity AS lEntity ON lEntity.[bk_aggregated_dim_legal_entity_id] = receipt.legal_entity_id AND lEntity.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receipt_type AS rType ON rType.[bk_aggregated_dim_receipt_type_id] = receipt.type_id AND rType.current_flag = 1
LEFT JOIN aggregated_odessa_dim_bank_account AS bank ON bank.[bk_aggregated_dim_bank_account_id] = receipt.[bank_account_id] AND bank.current_flag = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_receivable_invoice_detail
-- Depends on: vw_lease_finance_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_receivable_invoice_detail
AS
SELECT *
FROM
(
SELECT      

			fDetails.tax_balance_amount,
			fDetails.effective_balance_amount,
			fDetails.effective_tax_balance_amount,
			fDetails.invoice_amount_amount,
			fDetails.invoice_tax_amount_amount,
			fDetails.balance_amount,
			fDetails.receivable_amount_amount,
			fDetails.tax_amount_amount,	
			fDetails.sk_aggregated_dim_receivable,				

			customer.company_name AS customer_name,
			customer.external_reference_id AS customer_number,
			dInvoice.bk_aggregated_dim_receivable_invoice_id,
			dInvoiceCurrent.sk_aggregated_dim_receivable_invoice,	
			dInvoiceCurrent.days_late_count,
			fDetails.[sk_aggregated_dim_customer] AS customer_id,

			dDetail.entity_type,
			contract.sequence_number,				
			
			branch.branch_name as branch_name,

			dDate.bk_aggregated_dim_date as due_date,
			DATEDIFF(day, dDate.bk_aggregated_dim_date, GETDATE()) AS days_since_due,	

			pType.transaction_type as product_name,
			rType.name AS receivable_type,
			invoiceDate.bk_aggregated_dim_date AS invoice_date,
			dInvoice.number AS invoice_number,
			receivable.bk_aggregated_dim_receivable_id AS receivable_id,
			contract.bk_aggregated_dim_contract_id AS contract_id,
			contract.status as contract_status,
			ROW_NUMBER() OVER(PARTITION BY dInvoice.bk_aggregated_dim_receivable_invoice_id ORDER BY fDetails.sk_aggregated_dim_date_record DESC, fDetails.sk_aggregated_dim_time_record DESC) AS current_invoice          


FROM aggregated_odessa_fact_receivable_invoice_detail AS fDetails
JOIN aggregated_odessa_dim_receivable_invoice AS dInvoice ON dInvoice.sk_aggregated_dim_receivable_invoice = fDetails.sk_aggregated_dim_receivable_invoice
JOIN aggregated_odessa_dim_receivable_invoice AS dInvoiceCurrent ON dInvoiceCurrent.bk_aggregated_dim_receivable_invoice_id = dInvoice.bk_aggregated_dim_receivable_invoice_id AND dInvoiceCurrent.current_flag = 1
JOIN aggregated_odessa_dim_receivable_invoice_detail AS dDetail ON dDetail.sk_aggregated_dim_receivable_invoice_detail = fDetails.sk_aggregated_dim_receivable_invoice_detail AND dDetail.current_flag = 1
JOIN aggregated_odessa_dim_receivable AS receivable ON receivable.sk_aggregated_dim_receivable = fDetails.sk_aggregated_dim_receivable --AND receivable.current_flag = 1
JOIN aggregated_odessa_dim_contract AS contract ON contract.bk_aggregated_dim_contract_id = dDetail.entity_id AND contract.current_flag = 1
LEFT JOIN vw_lease_finance_detail AS lease ON lease.sk_current_dim_contract = contract.sk_aggregated_dim_contract 
LEFT JOIN aggregated_odessa_dim_branch AS branch ON branch.sk_aggregated_dim_branch = lease.sk_aggregated_dim_branch AND branch.current_flag = 1
LEFT JOIN aggregated_odessa_dim_customer AS customer ON customer.sk_aggregated_dim_customer = lease.sk_current_dim_customer
JOIN aggregated_odessa_dim_deal_product_type AS pType ON pType.bk_aggregated_dim_deal_product_type_id = contract.deal_product_type_id AND pType.current_flag = 1 
JOIN aggregated_odessa_dim_date as dDate ON dDate.sk_aggregated_dim_date = fDetails.sk_aggregated_dim_due_date
JOIN aggregated_odessa_dim_receivable_type AS rType ON rType.sk_aggregated_dim_receivable_type = fDetails.sk_aggregated_dim_receivable_type AND rType.current_flag = 1 
JOIN aggregated_odessa_dim_date AS invoiceDate ON invoiceDate.sk_aggregated_dim_date = fDetails.sk_aggregated_dim_invoice_run_date
) AS a 
WHERE a.current_invoice = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_receivable_invoices
-- Depends on: vw_receivable_invoice_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_receivable_invoices
AS
SELECT      
            SUM([tax_balance_amount]) AS tax_balance_amount,
			SUM([effective_balance_amount]) AS effective_balance_amount,
			SUM([effective_tax_balance_amount]) AS effective_tax_balance_amount,
			SUM([invoice_amount_amount]) AS invoice_amount_amount,
			SUM([invoice_tax_amount_amount]) AS invoice_tax_amount_amount,
			SUM([balance_amount]) AS balance_amount,
			SUM([receivable_amount_amount]) AS receivable_amount_amount,
			SUM([tax_amount_amount]) AS tax_amount_amount,
			MAX(days_late_count) AS days_late_count,
			MAX(days_since_due) AS days_since_due,				
			[customer_name],
			[customer_number],
			customer_id,
			[bk_aggregated_dim_receivable_invoice_id],
			[sequence_number],
			[contract_id],
			contract_status,
			[branch_name],
			[entity_type],
			[due_date],
			[product_name],
			[receivable_type],
			[invoice_date],
			[invoice_number]

FROM vw_receivable_invoice_detail 
GROUP BY 
			[customer_name],
			[customer_number],
			customer_id,
			[bk_aggregated_dim_receivable_invoice_id],
			[sequence_number],
			[contract_id],
			contract_status,
			[branch_name],
			[entity_type],
			[due_date],
			[product_name],
			[receivable_type],
			[invoice_date],
			[invoice_number]

;
GO
-- ----------------------------------------------------------
-- View: vw_lease_receivables
-- Depends on: vw_receivable_invoices
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_lease_receivables
AS
SELECT a.*
	   ,b.next_due_date
	   ,CASE WHEN a.effective_balance_amount > 0 THEN days_late_count ELSE 0 END AS days_past_due   
FROM
(
SELECT 
		SUM(tax_balance_amount) AS tax_balance_amount,
		SUM(effective_balance_amount) AS effective_balance_amount,
		SUM(effective_tax_balance_amount) AS effective_tax_balance_amount,
		SUM(invoice_amount_amount) AS invoice_amount_amount,
		SUM(invoice_tax_amount_amount) AS invoice_tax_amount_amount,
		SUM(balance_amount) AS balance_amount,
		SUM(receivable_amount_amount) AS receivable_amount_amount,
		SUM(tax_amount_amount) AS tax_amount_amount,
		MAX(days_late_count) AS days_late_count,
		MAX(days_since_due) AS days_since_due,	
		[customer_name],
		[customer_number],
		[sequence_number],
		[contract_id],
		[customer_id],
		[product_name]
FROM vw_receivable_invoices AS receivables
GROUP BY
		[customer_name],
		[customer_number],
		[customer_id],
		[sequence_number],
		[contract_id],
		[product_name]
) AS a
JOIN 
(
	SELECT contract_id, MIN(due_date) AS next_due_date
	FROM vw_receivable_invoices
	WHERE due_date >= GETDATE()
	GROUP BY contract_id
) AS b
ON a.contract_id = b.contract_id

;
GO
-- ----------------------------------------------------------
-- View: vw_customer_receivables
-- Depends on: vw_lease_receivables
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_customer_receivables
AS
SELECT 
		SUM(tax_balance_amount) AS tax_balance_amount,
		SUM(effective_balance_amount) AS effective_balance_amount,
		SUM(effective_tax_balance_amount) AS effective_tax_balance_amount,
		SUM(invoice_amount_amount) AS invoice_amount_amount,
		SUM(invoice_tax_amount_amount) AS invoice_tax_amount_amount,
		SUM(balance_amount) AS balance_amount,
		SUM(receivable_amount_amount) AS receivable_amount_amount,
		SUM(tax_amount_amount) AS tax_amount_amount,
		SUM(days_late_count) AS days_late_count,
		customer_id
FROM vw_lease_receivables AS receivables
GROUP BY
		customer_id

;
GO
-- ----------------------------------------------------------
-- View: vw_customer
-- Depends on: vw_customer_assignments, vw_customer_receivables, vw_lease_contracts
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_customer
AS
SELECT *
FROM
(
SELECT 
			ROW_NUMBER() OVER(PARTITION BY customer.bk_aggregated_dim_customer_id ORDER BY exposure.[exposure_date] DESC, policy.activation_date DESC) AS is_current_exposure,
			customer.current_flag,
			customer.external_reference_id,
			customer.primary_role,
			customer.vat_registration_number,
			customer.sic_code_id,
			customer.party_number,
			classificationCode.code AS sic_code,
			classificationCode.description AS sic_desc,				
			customer.organization_id,
			customer.party_name,
			customer.incorporation_date,
			customer.default_automated_payment_method,
			customer.company_name,
			customer.creation_date,
			customer.current_role,
			customer.status,
			customer.credit_term,
			customer.next_review_date,
			customer.invoice_grace_days,
			customer.invoice_lead_days,
			customer.credit_review_frequency,
			customer.credit_score,
			customer.annual_credit_review_date,
			customer.sk_aggregated_dim_customer,
			customer.bk_aggregated_dim_customer_id AS customer_id,
			customer.activation_date,
			exposure.total_proposed_customer_exposure_amount,
        	exposure.bk_aggregated_dim_customer_exposure_id AS exposure_id,			
			cSummary.primary_customer_amount,
			policy.[expiration_date] AS policy_expiration_date,
			DATEDIFF(MONTH, GETDATE(), customer.next_review_date) AS months_to_annual_review,
			policy.[type] AS policy_type,		
            policy.[policy_number],
			salesRep.employee_name AS account_manager,
			invoices.effective_balance_amount,
						
			leases.nbv_amount,
			leases.customer_cost_amount,
			leases.rent_amount,
			leases.accumulated_depreciation_amount,
			leases.fmv_amount,
			leases.initial_customer_cost_amount,
			leases.total_nbv_amount,
			leases.capitalized_additional_charge_amount,
			leases.asset_budget_value,
			leases.total_charge_to_customer,
			leases.number_of_assets,
			leases.yield 					

FROM aggregated_odessa_dim_customer AS customer
LEFT JOIN aggregated_odessa_dim_insurance_policy AS policy ON policy.customer_id = customer.bk_aggregated_dim_customer_id AND policy.current_flag = 1 AND is_active = 1
LEFT JOIN aggregated_odessa_dim_customer_exposure AS exposure ON exposure.exposure_customer_id = customer.bk_aggregated_dim_customer_id AND exposure.current_flag = 1 AND exposure.is_active = 1
JOIN aggregated_odessa_dim_credit_summary_exposure AS cSummary ON cSummary.customer_id = customer.bk_aggregated_dim_customer_id AND cSummary.current_flag = 1 AND cSummary.exposure_type = 'EF'
LEFT JOIN aggregated_odessa_dim_classification_code AS classificationCode ON customer.sic_code_id = classificationCode.bk_aggregated_dim_classification_code_id AND classificationCode.current_flag = 1
LEFT JOIN vw_customer_assignments AS salesRep ON salesRep.customer_id = customer.bk_aggregated_dim_customer_id AND salesRep.system_defined_name = 'SalesRep'
LEFT JOIN vw_customer_receivables AS invoices ON invoices.customer_id = customer.bk_aggregated_dim_customer_id 
LEFT JOIN 
	(
		SELECT 
				lease.customer_id,						
				SUM(nbv_amount) AS nbv_amount,
				SUM(customer_cost_amount) AS customer_cost_amount,
				SUM(rent_amount) AS rent_amount,
				SUM(accumulated_depreciation_amount) AS accumulated_depreciation_amount,
				SUM(fmv_amount) AS fmv_amount,
				SUM(initial_customer_cost_amount) AS initial_customer_cost_amount,
				SUM(nbv_amount) AS total_nbv_amount,
				SUM(capitalized_additional_charge_amount) AS capitalized_additional_charge_amount,
				SUM(asset_budget_value) AS asset_budget_value,
				SUM(total_charge_to_customer) AS total_charge_to_customer,
				SUM(number_of_assets) AS number_of_assets,
				AVG(total_yield) AS yield

		FROM vw_lease_contracts AS lease
		GROUP BY lease.customer_id
	) AS leases ON customer.bk_aggregated_dim_customer_id = leases.customer_id 
WHERE customer.current_flag = 1
) as a
WHERE a.is_current_exposure = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_receivables
-- Depends on: vw_receivable_invoice_detail
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_receivables
AS
SELECT      
            SUM([tax_balance_amount]) AS tax_balance_amount,
			SUM([effective_balance_amount]) AS effective_balance_amount,
			SUM([effective_tax_balance_amount]) AS effective_tax_balance_amount,
			SUM([invoice_amount_amount]) AS invoice_amount_amount,
			SUM([invoice_tax_amount_amount]) AS invoice_tax_amount_amount,
			SUM([balance_amount]) AS balance_amount,
			SUM([receivable_amount_amount]) AS receivable_amount_amount,
			SUM([tax_amount_amount]) AS tax_amount_amount,
			MAX(days_late_count) AS days_late_count,
			MAX(days_since_due) AS days_since_due,				
			[customer_name],
			[customer_number],
			customer_id,
			[bk_aggregated_dim_receivable_invoice_id],
			[receivable_id],			
			[sequence_number],
			[contract_id],
			[branch_name],
			[entity_type],
			[due_date],
			[product_name],
			[receivable_type],
			[invoice_date],
			[invoice_number]

FROM vw_receivable_invoice_detail 
GROUP BY 
			[customer_name],
			[customer_number],
			[customer_id],
			[bk_aggregated_dim_receivable_invoice_id],
			[receivable_id],
			[sequence_number],
			[contract_id],
			[branch_name],
			[entity_type],
			[due_date],
			[product_name],
			[receivable_type],
			[invoice_date],
			[invoice_number]

;
GO
-- ----------------------------------------------------------
-- View: vw_sundry
-- Depends on: vw_receivables
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_sundry
AS
SELECT * --COUNT(*)
FROM
(
SELECT     
			sundry.amount_amount,
			sundry.bk_aggregated_dim_sundry_id,
			sundry.entity_type,
			sundry.payable_tax_detail_id,
			sundry.r2_c_invoice_number,
			sundry.projected_vat_amount_amount,
			sundry.status,
			sundry.cost_center_id,
			sundry.branch_id,
			sundry.lineof_business_id,
			sundry.customer_id,
			sundry.receivable_id,
			sundry.currency_id,
			sundry.receivable_code_id,
			sundry.bill_to_id,
			sundry.legal_entity_id,
			sundry.contract_id,
			sundry.sundry_type,
			sundry.receivable_due_date,
			sundry.invoice_comment,
			sundry.[po_number],
			sundry.[customer_po_number],
			sundry.[created_time] AS sundry_created_date,

			rCode.name receivable_code,
		    rCode.name AS charge_name,
			invoiceReceivable.invoice_number,
			contract.sequence_number,
			contract.alias AS aag_contract_number,
			pType.transaction_type AS product_name2,
			customer.company_name,
			taxes.balance_amount AS tax_balance_amount2,
			
			invoiceReceivable.invoice_date,
			invoiceReceivable.[due_date] AS invoice_due_date,
			invoiceReceivable.[product_name],
			invoiceReceivable.[bk_aggregated_dim_receivable_invoice_id] AS invoice_id,
			invoiceReceivable.receivable_type,

			invoiceReceivable.[receivable_amount_amount],
			invoiceReceivable.[tax_balance_amount],
			invoiceReceivable.[effective_tax_balance_amount],
			invoiceReceivable.[effective_balance_amount],
			invoiceReceivable.balance_amount,
    		sundry.amount_amount + sundry.[projected_vat_amount_amount] AS total_due_amount,
    		taxes.[balance_amount] + invoiceReceivable.balance_amount AS total_balance_amount						

FROM aggregated_odessa_dim_sundry AS sundry
LEFT JOIN aggregated_odessa_dim_receivable_code AS rCode ON rCode.bk_aggregated_dim_receivable_code_id = sundry.receivable_code_id AND rCode.current_flag = 1
LEFT JOIN aggregated_odessa_dim_contract AS contract ON contract.bk_aggregated_dim_contract_id = sundry.contract_id AND contract.current_flag = 1
LEFT JOIN aggregated_odessa_dim_deal_product_type AS pType ON pType.bk_aggregated_dim_deal_product_type_id = contract.deal_product_type_id AND pType.current_flag = 1
LEFT JOIN aggregated_odessa_dim_customer AS customer ON sundry.customer_id = customer.bk_aggregated_dim_customer_id AND customer.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receivable AS receivables ON receivables.bk_aggregated_dim_receivable_id = sundry.receivable_id AND receivables.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receivable_tax AS taxes ON taxes.receivable_id = receivables.bk_aggregated_dim_receivable_id AND taxes.current_flag = 1
LEFT JOIN vw_receivables AS invoiceReceivable ON invoiceReceivable.receivable_id = receivables.bk_aggregated_dim_receivable_id
) AS a

;
GO
-- ----------------------------------------------------------
-- View: vw_sundry_details
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_sundry_details
AS

SELECT DISTINCT 

	sundry.[bk_aggregated_dim_sundry_id]
	,sundry.[sundry_type]
	,sundry.[amount_amount]
	,sundry.[amount_currency]
	,sundry.[receivable_due_date]
	--,sundry.[start_date]
	--,sundry.[end_date]
	,sundry.[created_time]
	,sundry.[sk_aggregated_dim_sundry]
	,sundry.[r2_c_invoice_number]
	,sundry.[projected_vat_amount_amount]
	,sundry.[payable_amount_amount]
	,sundry.[cost_center_id]
	,sundry.[branch_id]
	,sundry.[lineof_business_id]
	,sundry.[bill_to_id]
	,sundry.[payable_code_id]
	,sundry.[contract_id]
	,sundry.[customer_id]
	,sundry.vendor_id
	,sundry.[is_active]
	,sundry.[payable_due_date]
	,sundry.[invoice_comment]
    ,sundry.amount_amount + sundry.[projected_vat_amount_amount] AS total_due_amount
	,taxes.[balance_amount]
	,ReceivableCode.name AS Recharge_Fee_Name
	,PayableCode.name AS Expense_Fee_Name
	,Customer.company_name
	,SundryDetail.asset_id


FROM aggregated_odessa_dim_sundry AS sundry
LEFT JOIN aggregated_odessa_dim_receivable AS receivables ON receivables.[bk_aggregated_dim_receivable_id] = sundry.[receivable_id] AND receivables.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receivable_code AS ReceivableCode ON sundry.[receivable_code_id] = ReceivableCode.[bk_aggregated_dim_receivable_code_id] AND ReceivableCode.current_flag = 1 AND ReceivableCode.is_active = 1
LEFT JOIN aggregated_odessa_dim_payable_code AS PayableCode ON sundry.payable_code_id = PayableCode.[bk_aggregated_dim_payable_code_id] AND PayableCode.current_flag = 1
LEFT JOIN aggregated_odessa_dim_receivable_tax AS taxes ON taxes.[receivable_id] = receivables.[bk_aggregated_dim_receivable_id] AND taxes.current_flag = 1 AND taxes.is_active = 1
LEFT JOIN aggregated_odessa_dim_customer AS Customer ON sundry.customer_id = Customer.[bk_aggregated_dim_customer_id] AND Customer.current_flag = 1
LEFT JOIN aggregated_odessa_dim_sundry_detail AS SundryDetail ON sundry.[bk_aggregated_dim_sundry_id] = SundryDetail.[sundry_id] AND SundryDetail.current_flag = 1 AND SundryDetail.is_active = 1

where sundry.current_flag = 1 AND sundry.is_active = 1

;
GO
-- ----------------------------------------------------------
-- View: vw_sundry_recurring_charges
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_sundry_recurring_charges
AS
SELECT *
FROM  
(
SELECT DISTINCT 
		
			SundryRecurring.[bk_aggregated_dim_sundry_recurring_id],
			SundryRecurring.[sundry_type],
			SundryRecurring.[invoice_comment],
			SundryRecurring.[current_flag],
			SundryRecurring.[sk_aggregated_dim_sundry_recurring],
			SundryRecurring.[branch_id],
			SundryRecurring.[regular_amount_amount],
			SundryRecurring.[regular_amount_currency],
			SundryRecurring.[lineof_business_id],
			SundryRecurring.[status],
			SundryRecurring.[payable_amount_amount],
			SundryRecurring.[payable_amount_currency],
			SundryRecurring.[bill_to_id],
			SundryRecurring.[vendor_id],
			SundryRecurring.[legal_entity_id],
			SundryRecurring.[contract_id],
			SundryRecurring.[customer_id],
			SundryRecurring.[receivable_code_id],
			SundryRecurring.[frequency],
			SundryRecurring.[due_day],
			SundryRecurring.[is_asset_based],
			SundryRecurring.[is_rental_based],
			SundryRecurring.[number_of_payments],

			ReceivableCode.name,
			ReceivableCode.name AS 	charge_name,		

    		contract.sequence_number

FROM [aggregated_odessa_dim_sundry_recurring] AS SundryRecurring

LEFT JOIN aggregated_odessa_dim_receivable_code AS ReceivableCode ON SundryRecurring.[receivable_code_id] = ReceivableCode.[bk_aggregated_dim_receivable_code_id] AND ReceivableCode.current_flag = 1
LEFT JOIN aggregated_odessa_dim_contract contract ON SundryRecurring.[contract_id] = contract.[bk_aggregated_dim_contract_id] AND contract.current_flag = 1

WHERE

SundryRecurring.current_flag = 1
) AS a

;
GO
-- ----------------------------------------------------------
-- View: vw_sundry_recurring_charge_details
-- Depends on: vw_sundry_recurring_charges
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_sundry_recurring_charge_details
AS 
SELECT *
from
(
    SELECT 

    SundryRecurringDetail.[bk_aggregated_dim_sundry_recurring_payment_detail_id],
    SundryRecurringDetail.[amount_amount],
    SundryRecurringDetail.[amount_currency],
    SundryRecurringDetail.[current_flag],
    SundryRecurringDetail.[sundry_recurring_id],
    SundryRecurringDetail.[payable_amount_amount],
    SundryRecurringDetail.[payable_amount_currency],
    SundryRecurringDetail.[bill_to_id],


    SR.sequence_number,
    SR.contract_id AS contract_id,
    SR.charge_name,
    SundryRecurringDetail.asset_id,
    SundryRecurringDetail.[amount_amount] sundry_amount,
    SundryRecurringDetail.[vat_amount_amount] vat_amount,
    AC.[amount_amount] additional_charge_amount    

    FROM aggregated_odessa_dim_sundry_recurring_payment_detail AS SundryRecurringDetail
    JOIN vw_sundry_recurring_charges AS SR ON SundryRecurringDetail.[bk_aggregated_dim_sundry_recurring_payment_detail_id] = SR.[bk_aggregated_dim_sundry_recurring_id]

    JOIN aggregated_odessa_dim_lease_finance_additional_charge LFAC ON LFAC.[recurring_sundry_id] = SR.[bk_aggregated_dim_sundry_recurring_id]
    JOIN aggregated_odessa_dim_additional_charge AS AC ON AC.[bk_aggregated_dim_additional_charge_id] = LFAC.[additional_charge_id]
  
    WHERE SundryRecurringDetail.current_flag = 1
    AND AC.current_flag = 1
    AND SR.current_flag = 1
    AND LFAC.current_flag = 1
   
) as a

;
GO
-- ----------------------------------------------------------
-- View: vw_sundry_recurring_schedule
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_sundry_recurring_schedule
AS 
(
	SELECT [sk_aggregated_dim_sundry_recurring_payment_schedule],
			[current_flag],
			[payable_amount_currency],
			[receivable_id],
			[payable_id],
			[sundry_recurring_id],
			[payable_amount_amount],
			[created_time],
			[bk_aggregated_dim_sundry_recurring_payment_schedule_id],
			[due_date],
			[amount_amount],
			[amount_currency]
	FROM [aggregated_odessa_dim_sundry_recurring_payment_schedule]
	WHERE current_flag = 1
)

;
GO
