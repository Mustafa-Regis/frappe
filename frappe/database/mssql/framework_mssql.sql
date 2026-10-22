-- Core Elements to install Frappe Framework on Microsoft SQL Server

--
-- Table structure for table [tabDocField]
--
DROP TABLE IF EXISTS [tabDocField];
CREATE TABLE [tabDocField] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [fieldname] nvarchar(255) DEFAULT NULL,
  [label] nvarchar(255) DEFAULT NULL,
  [oldfieldname] nvarchar(255) DEFAULT NULL,
  [fieldtype] nvarchar(255) DEFAULT NULL,
  [oldfieldtype] nvarchar(255) DEFAULT NULL,
  [options] nvarchar(max),
  [search_index] smallint NOT NULL DEFAULT 0,
  [hidden] smallint NOT NULL DEFAULT 0,
  [set_only_once] smallint NOT NULL DEFAULT 0,
  [show_dashboard] smallint NOT NULL DEFAULT 0,
  [allow_in_quick_entry] smallint NOT NULL DEFAULT 0,
  [print_hide] smallint NOT NULL DEFAULT 0,
  [report_hide] smallint NOT NULL DEFAULT 0,
  [reqd] smallint NOT NULL DEFAULT 0,
  [bold] smallint NOT NULL DEFAULT 0,
  [in_global_search] smallint NOT NULL DEFAULT 0,
  [collapsible] smallint NOT NULL DEFAULT 0,
  [unique] smallint NOT NULL DEFAULT 0,
  [no_copy] smallint NOT NULL DEFAULT 0,
  [allow_on_submit] smallint NOT NULL DEFAULT 0,
  [show_preview_popup] smallint NOT NULL DEFAULT 0,
  [trigger] nvarchar(255) DEFAULT NULL,
  [collapsible_depends_on] nvarchar(max),
  [mandatory_depends_on] nvarchar(max),
  [read_only_depends_on] nvarchar(max),
  [depends_on] nvarchar(max),
  [permlevel] bigint NOT NULL DEFAULT 0,
  [ignore_user_permissions] smallint NOT NULL DEFAULT 0,
  [width] nvarchar(255) DEFAULT NULL,
  [print_width] nvarchar(255) DEFAULT NULL,
  [columns] bigint NOT NULL DEFAULT 0,
  [default] nvarchar(max),
  [description] nvarchar(max),
  [in_list_view] smallint NOT NULL DEFAULT 0,
  [fetch_if_empty] smallint NOT NULL DEFAULT 0,
  [in_filter] smallint NOT NULL DEFAULT 0,
  [remember_last_selected_value] smallint NOT NULL DEFAULT 0,
  [ignore_xss_filter] smallint NOT NULL DEFAULT 0,
  [print_hide_if_no_value] smallint NOT NULL DEFAULT 0,
  [allow_bulk_edit] smallint NOT NULL DEFAULT 0,
  [in_standard_filter] smallint NOT NULL DEFAULT 0,
  [in_preview] smallint NOT NULL DEFAULT 0,
  [read_only] smallint NOT NULL DEFAULT 0,
  [precision] nvarchar(255) DEFAULT NULL,
  [max_height] nvarchar(10) DEFAULT NULL,
  [length] bigint NOT NULL DEFAULT 0,
  [translatable] smallint NOT NULL DEFAULT 0,
  [hide_border] smallint NOT NULL DEFAULT 0,
  [hide_days] smallint NOT NULL DEFAULT 0,
  [hide_seconds] smallint NOT NULL DEFAULT 0,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabDocField_parent] ON [tabDocField] ([parent]);
CREATE INDEX [idx_tabDocField_label] ON [tabDocField] ([label]);
CREATE INDEX [idx_tabDocField_fieldtype] ON [tabDocField] ([fieldtype]);
CREATE INDEX [idx_tabDocField_fieldname] ON [tabDocField] ([fieldname]);

--
-- Table structure for table [tabDocPerm]
--
DROP TABLE IF EXISTS [tabDocPerm];
CREATE TABLE [tabDocPerm] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [permlevel] bigint DEFAULT 0,
  [role] nvarchar(255) DEFAULT NULL,
  [match] nvarchar(255) DEFAULT NULL,
  [read] smallint NOT NULL DEFAULT 1,
  [write] smallint NOT NULL DEFAULT 1,
  [create] smallint NOT NULL DEFAULT 1,
  [submit] smallint NOT NULL DEFAULT 0,
  [cancel] smallint NOT NULL DEFAULT 0,
  [delete] smallint NOT NULL DEFAULT 1,
  [amend] smallint NOT NULL DEFAULT 0,
  [report] smallint NOT NULL DEFAULT 1,
  [export] smallint NOT NULL DEFAULT 1,
  [import] smallint NOT NULL DEFAULT 0,
  [share] smallint NOT NULL DEFAULT 1,
  [print] smallint NOT NULL DEFAULT 1,
  [email] smallint NOT NULL DEFAULT 1,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabDocPerm_parent] ON [tabDocPerm] ([parent]);

--
-- Table structure for table [tabDocType Action]
--
DROP TABLE IF EXISTS [tabDocType Action];
CREATE TABLE [tabDocType Action] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [label] nvarchar(140) NOT NULL,
  [group] nvarchar(max) DEFAULT NULL,
  [action_type] nvarchar(140) NOT NULL,
  [action] nvarchar(140) NOT NULL,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabDocType_Action_parent] ON [tabDocType Action] ([parent]);

--
-- Table structure for table [tabDocType Link]
--
DROP TABLE IF EXISTS [tabDocType Link];
CREATE TABLE [tabDocType Link] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [label] nvarchar(140) DEFAULT NULL,
  [group] nvarchar(140) DEFAULT NULL,
  [link_doctype] nvarchar(140) NOT NULL,
  [link_fieldname] nvarchar(140) NOT NULL,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabDocType_Link_parent] ON [tabDocType Link] ([parent]);

--
-- Table structure for table [tabDocType]
--
DROP TABLE IF EXISTS [tabDocType];
CREATE TABLE [tabDocType] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [idx] bigint NOT NULL DEFAULT 0,
  [search_fields] nvarchar(255) DEFAULT NULL,
  [issingle] smallint NOT NULL DEFAULT 0,
  [is_virtual] smallint NOT NULL DEFAULT 0,
  [is_tree] smallint NOT NULL DEFAULT 0,
  [istable] smallint NOT NULL DEFAULT 0,
  [editable_grid] smallint NOT NULL DEFAULT 1,
  [track_changes] smallint NOT NULL DEFAULT 0,
  [module] nvarchar(255) DEFAULT NULL,
  [restrict_to_domain] nvarchar(255) DEFAULT NULL,
  [app] nvarchar(255) DEFAULT NULL,
  [autoname] nvarchar(255) DEFAULT NULL,
  [naming_rule] nvarchar(40) DEFAULT NULL,
  [title_field] nvarchar(255) DEFAULT NULL,
  [image_field] nvarchar(255) DEFAULT NULL,
  [timeline_field] nvarchar(255) DEFAULT NULL,
  [sort_field] nvarchar(255) DEFAULT NULL,
  [sort_order] nvarchar(255) DEFAULT NULL,
  [description] nvarchar(max),
  [colour] nvarchar(255) DEFAULT NULL,
  [read_only] smallint NOT NULL DEFAULT 0,
  [in_create] smallint NOT NULL DEFAULT 0,
  [menu_index] bigint DEFAULT NULL,
  [parent_node] nvarchar(255) DEFAULT NULL,
  [smallicon] nvarchar(255) DEFAULT NULL,
  [allow_copy] smallint NOT NULL DEFAULT 0,
  [allow_rename] smallint NOT NULL DEFAULT 0,
  [allow_import] smallint NOT NULL DEFAULT 0,
  [hide_toolbar] smallint NOT NULL DEFAULT 0,
  [track_seen] smallint NOT NULL DEFAULT 0,
  [max_attachments] bigint NOT NULL DEFAULT 0,
  [print_outline] nvarchar(255) DEFAULT NULL,
  [document_type] nvarchar(255) DEFAULT NULL,
  [icon] nvarchar(255) DEFAULT NULL,
  [color] nvarchar(255) DEFAULT NULL,
  [tag_fields] nvarchar(255) DEFAULT NULL,
  [subject] nvarchar(255) DEFAULT NULL,
  [_last_update] nvarchar(32) DEFAULT NULL,
  [engine] nvarchar(20) DEFAULT 'InnoDB',
  [default_print_format] nvarchar(255) DEFAULT NULL,
  [is_submittable] smallint NOT NULL DEFAULT 0,
  [show_name_in_global_search] smallint NOT NULL DEFAULT 0,
  [_user_tags] nvarchar(255) DEFAULT NULL,
  [custom] smallint NOT NULL DEFAULT 0,
  [beta] smallint NOT NULL DEFAULT 0,
  [has_web_view] smallint NOT NULL DEFAULT 0,
  [allow_guest_to_view] smallint NOT NULL DEFAULT 0,
  [route] nvarchar(255) DEFAULT NULL,
  [is_published_field] nvarchar(255) DEFAULT NULL,
  [website_search_field] nvarchar(255) DEFAULT NULL,
  [email_append_to] smallint NOT NULL DEFAULT 0,
  [subject_field] nvarchar(255) DEFAULT NULL,
  [sender_field] nvarchar(255) DEFAULT NULL,
  [show_title_field_in_link] smallint NOT NULL DEFAULT 0,
  [migration_hash] nvarchar(255) DEFAULT NULL,
  [translated_doctype] smallint NOT NULL DEFAULT 0,
  PRIMARY KEY ([name])
);

--
-- Table structure for table [tabSeries]
--
DROP TABLE IF EXISTS [tabSeries];
CREATE TABLE [tabSeries] (
  [name] nvarchar(100) NOT NULL,
  [current] bigint NOT NULL DEFAULT 0,
  PRIMARY KEY ([name])
);

--
-- Table structure for table [tabSessions]
--
DROP TABLE IF EXISTS [tabSessions];
CREATE TABLE [tabSessions] (
  [user] nvarchar(255) DEFAULT NULL,
  [sid] nvarchar(255) DEFAULT NULL,
  [sessiondata] nvarchar(max),
  [ipaddress] nvarchar(16) DEFAULT NULL,
  [lastupdate] datetime2(6) DEFAULT NULL,
  [status] nvarchar(20) DEFAULT NULL
);

CREATE INDEX [idx_tabSessions_sid] ON [tabSessions] ([sid]);

--
-- Table structure for table [tabSingles]
--
DROP TABLE IF EXISTS [tabSingles];
CREATE TABLE [tabSingles] (
  [doctype] nvarchar(255) DEFAULT NULL,
  [field] nvarchar(255) DEFAULT NULL,
  [value] nvarchar(max)
);

CREATE INDEX [idx_tabSingles_doctype_field] ON [tabSingles] ([doctype], [field]);

--
-- Table structure for table [__Auth]
--
DROP TABLE IF EXISTS [__Auth];
CREATE TABLE [__Auth] (
  [doctype] nvarchar(140) NOT NULL,
  [name] nvarchar(255) NOT NULL,
  [fieldname] nvarchar(140) NOT NULL,
  [password] nvarchar(max) NOT NULL,
  [encrypted] int NOT NULL DEFAULT 0,
  PRIMARY KEY ([doctype], [name], [fieldname])
);

--
-- Table structure for table [tabFile]
--
DROP TABLE IF EXISTS [tabFile];
CREATE TABLE [tabFile] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [file_name] nvarchar(255) DEFAULT NULL,
  [file_url] nvarchar(255) DEFAULT NULL,
  [module] nvarchar(255) DEFAULT NULL,
  [attached_to_name] nvarchar(255) DEFAULT NULL,
  [file_size] bigint NOT NULL DEFAULT 0,
  [attached_to_doctype] nvarchar(255) DEFAULT NULL,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabFile_parent] ON [tabFile] ([parent]);
CREATE INDEX [idx_tabFile_attached_to_name] ON [tabFile] ([attached_to_name]);
CREATE INDEX [idx_tabFile_attached_to_doctype] ON [tabFile] ([attached_to_doctype]);

--
-- Table structure for table [tabDefaultValue]
--
DROP TABLE IF EXISTS [tabDefaultValue];
CREATE TABLE [tabDefaultValue] (
  [name] nvarchar(255) NOT NULL,
  [creation] datetime2(6) DEFAULT NULL,
  [modified] datetime2(6) DEFAULT NULL,
  [modified_by] nvarchar(255) DEFAULT NULL,
  [owner] nvarchar(255) DEFAULT NULL,
  [docstatus] smallint NOT NULL DEFAULT 0,
  [parent] nvarchar(255) DEFAULT NULL,
  [parentfield] nvarchar(255) DEFAULT NULL,
  [parenttype] nvarchar(255) DEFAULT NULL,
  [idx] bigint NOT NULL DEFAULT 0,
  [defvalue] nvarchar(max),
  [defkey] nvarchar(255) DEFAULT NULL,
  PRIMARY KEY ([name])
);

CREATE INDEX [idx_tabDefaultValue_parent] ON [tabDefaultValue] ([parent]);
CREATE INDEX [idx_tabDefaultValue_parent_defkey] ON [tabDefaultValue] ([parent], [defkey]);
