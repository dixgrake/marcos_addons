odoo.define('ncf_pos.models', function (require) {
    'use strict';

    var models = require('point_of_sale.models');
    var session = require('web.session');
    var Model = require('web.DataModel');

    models.load_fields("product.product", ["tracking"]);
    models.load_fields("res.company", ['street', 'street2', "city", 'state_id', 'zip', 'country_id']);
    models.load_fields("res.users", ['allow_payments', 'allow_delete_order', 'allow_discount', 'allow_edit_price', 'allow_delete_order', 'allow_refund', 'allow_delete_order_line', 'allow_cancel', 'allow_cash_refund', 'allow_credit', 'allow_line_rename']);
    models.load_fields("res.partner", ['property_account_position_id']);


    var PosModelSuper = models.PosModel;

    models.PosModel = models.PosModel.extend({
        initialize: function () {
            PosModelSuper.prototype.initialize.apply(this, arguments);
        },
        set_cashier: function (user) {
            this.cashier = user;
            this.chrome.check_allow_delete_order();
        },
        // send an array of orders to the server
        // available options:
        // - timeout: timeout for the rpc call in ms
        // returns a deferred that resolves with the list of
        // server generated ids for the sent orders
        _save_to_server: function (orders, options) {
            if (!orders || !orders.length) {
                var result = $.Deferred();
                result.resolve([]);
                return result;
            }

            options = options || {};

            var self = this;
            var timeout = typeof options.timeout === 'number' ? options.timeout : 97500 * orders.length;

            // we try to send the order. shadow prevents a spinner if it takes too long. (unless we are sending an invoice,
            // then we want to notify the user that we are waiting on something )
            var posOrderModel = new Model('pos.order');
            return posOrderModel.call('create_from_ui',
                [_.map(orders, function (order) {
                    order.to_invoice = options.to_invoice || false;
                    return order;
                })],
                undefined,
                {
                    shadow: !options.to_invoice,
                    timeout: timeout
                }
            ).then(function (server_ids) {
                _.each(orders, function (order) {
                    self.db.remove_order(order.id);
                });
                self.set('failed', false);
                return server_ids;
            }).fail(function (error, event) {
                if (error.code === 200) {    // Business Logic Error, not a connection problem
                    //if warning do not need to display traceback!!
                    if (error.data.exception_type == 'warning') {
                        delete error.data.debug;
                    }

                    // Hide error if already shown before ...
                    if ((!self.get('failed') || options.show_error) && !options.to_invoice) {
                        self.gui.show_popup('error-traceback', {
                            'title': error.data.message,
                            'body': error.data.debug
                        });
                    }
                    self.set('failed', error)
                }
                // prevent an error popup creation by the rpc failure
                // we want the failure to be silent as we send the orders in the background
                event.preventDefault();
                console.error('Failed to send orders:', orders);
            });
        }
    });

    var _order_line_super = models.Orderline.prototype;
    models.Orderline = models.Orderline.extend({
        initialize: function () {
            _order_line_super.initialize.apply(this, arguments);
            this.qty_allow_refund = this.qty_allow_refund || 0;
            this.refund_line_ref = this.refund_line_ref || false;

        },
        set_discount: function (discount) {
            var self = this;
            var cashier = self.pos.get_cashier();
            var disc = Math.min(Math.max(parseFloat(discount) || 0, 0), 100);
            if (disc <= cashier.allow_discount) {
                this.discount = disc;
                this.discountStr = '' + disc;
                this.trigger('change', this);
            }
        },
        set_qty_allow_refund: function (qty_allow_refund) {
            this.qty_allow_refund = qty_allow_refund;
            this.trigger('change', this);
        },
        get_qty_allow_refund: function () {
            return this.qty_allow_refund || 0;
        },
        set_refund_line_ref: function (refund_line_ref) {
            this.refund_line_ref = refund_line_ref || false;
            this.trigger('change', this)
        },
        get_refund_line_ref: function () {
            return this.refund_line_ref || false;
        },
        set_prodlot_id: function (product_serial_lot) {
            this.prodlot_id = product_serial_lot || false;
            this.trigger('change', this)
        },
        get_prodlot_id: function (serial_lot) {
            return this.prodlot_id || false;
        },
        export_as_JSON: function () {
            var json = _order_line_super.export_as_JSON.apply(this, arguments);
            json.qty_allow_refund = this.get_qty_allow_refund();
            json.refund_line_ref = this.get_refund_line_ref();
            json.prodlot_id = this.get_prodlot_id();
            return json
        },
        export_for_printing: function () {
            var json = _order_line_super.export_for_printing.apply(this, arguments);
            json.qty_allow_refund = this.get_qty_allow_refund();
            json.refund_line_ref = this.get_refund_line_ref();
            json.prodlot_id = this.get_prodlot_id();
            return json;
        }
    });

    var PaymentlineSuper = models.Paymentline.prototype;
    models.Paymentline = models.Paymentline.extend({
        initialize: function () {
            PaymentlineSuper.initialize.apply(this, arguments);
            this.type = this.type || 'payment'
            return this;
        },
        set_type: function (type) {
            this.type = type;
            this.trigger("change", this);
        },
        get_type: function () {
            return this.type;
        },
        export_as_JSON: function () {
            var res = PaymentlineSuper.export_as_JSON.apply(this, arguments);
            res.type = this.get_type();
            return res;
        },
        export_for_printing: function () {
            var res = PaymentlineSuper.export_for_printing.apply(this, arguments);
            res.type = this.get_type();
            return res
        }
    });

    var _super_order = models.Order.prototype;
    models.Order = models.Order.extend({
        initialize: function () {
            _super_order.initialize.apply(this, arguments);
            var self = this;
            this.quotation_type = this.quotation_type || false;
            this.order_type = this.order_type || "order";
            this.origin = this.origin || false;
            this.origin_ncf = this.origin_ncf || false;
            this.credit = this.credit || 0;
            this.credit_ncf = this.credit_ncf || "";
            this.ncf = this.ncf || "";
            this.invoice_type = this.invoice_type || "";
            this.fiscal_type = this.fiscal_type || "";

            if (!self.get_client()) {
                var default_partner_id = self.pos.db.get_partner_by_id(self.pos.config.default_partner_id[0]);
                self.set_client(default_partner_id);
            }
        },
        set_client: function (client) {
            var self = this;

            if (client) {
                _.each(self.pos.fiscal_positions, function (fiscal_position) {
                    if (client.property_account_position_id) {
                        if (fiscal_position.id === client.property_account_position_id[0]) {
                            self.fiscal_position = fiscal_position
                        }
                    } else if (fiscal_position.client_fiscal_type === "final") {
                        self.fiscal_position = fiscal_position
                    }
                });
            }
            this.assert_editable();
            this.set('client', client);
        },
        init_from_JSON: function (json) {
            _super_order.init_from_JSON.apply(this, arguments);
            this.quotation_type = json.quotation_type;
            this.order_type = json.order_type;
            this.origin = json.origin;
            this.origin_ncf = json.origin_ncf;
            return this
        },
        get_order_note: function () {
            return $("#wk_note_id").val();
        },
        set_quotation_type: function (quotation_type) {
            this.quotation_type = quotation_type;
            this.trigger('change', this);
        },
        get_quotation_type: function () {
            return this.quotation_type || false;
        },
        set_order_type: function (order_type) {
            this.order_type = order_type;
            this.trigger('change', this);
        },
        get_order_type: function () {
            return this.order_type || "order";
        },
        set_origin: function (origin) {
            this.origin = origin;
            this.trigger('change', this);
        },
        get_origin: function () {
            return this.origin || false
        },
        set_ncf: function (ncf) {
            this.ncf = ncf;
            this.trigger('change', this);
        },
        get_ncf: function () {
            return this.ncf || false
        },
        set_fiscal_type_name: function (fiscal_type_name) {
            this.fiscal_type_name = fiscal_type_name;
            this.trigger('change', this);
        },
        get_fiscal_type_name: function () {
            return this.fiscal_type_name || false
        },
        set_origin_ncf: function (origin_ncf) {
            this.origin_ncf = origin_ncf;
            this.trigger('change', this);
        },
        get_origin_ncf: function () {
            return this.origin_ncf || false
        },
        set_credit: function (credit) {
            this.credit = credit;
            this.trigger('change', this)
        },
        get_credit: function () {
            return this.credit || 0;
        },
        set_credit_ncf: function (credit) {
            this.credit_ncf = credit;
            this.trigger('change', this)
        },
        get_credit_ncf: function () {
            return this.credit_ncf || 0;
        },
        set_fiscal_type: function (credit) {
            this.fiscal_type = credit;
            this.trigger('change', this)
        },
        get_fiscal_type: function () {
            return this.fiscal_type || 0;
        },
        add_product: function (product, options) {
            if (product.qty_allow_refund == 0 && this.get_order_type() == "refund") {
                return
            }

            if (this._printed) {
                this.destroy();
                return this.pos.get_order().add_product(product, options);
            }
            this.assert_editable();
            options = options || {};
            var attr = JSON.parse(JSON.stringify(product));
            attr.pos = this.pos;
            attr.order = this;


            var line = new models.Orderline({}, {pos: this.pos, order: this, product: product});

            if (this.get_order_type() == "refund") {
                line.set_unit_price(product.refund_price);
                line.set_discount(product.refund_discount);
                line.set_note(product.refund_note);
                line.set_qty_allow_refund(product.qty_allow_refund);
                line.set_refund_line_ref(product.refund_line_ref);
                product.qty_allow_refund--;
            }

            if (options.prodlot_id !== undefined) {
                line.set_prodlot_id(options.prodlot_id)
            }

            if (options.quantity !== undefined) {
                line.set_quantity(options.quantity);
            }
            if (options.price !== undefined) {
                line.set_unit_price(options.price);
            }
            if (options.discount !== undefined) {
                line.set_discount(options.discount);
            }

            if (options.extras !== undefined) {
                for (var prop in options.extras) {
                    line[prop] = options.extras[prop];
                }
            }

            var last_orderline = this.get_last_orderline();
            if (last_orderline && last_orderline.can_be_merged_with(line) && options.merge !== false) {
                last_orderline.merge(line);
            } else {
                this.orderlines.add(line);
            }
            this.select_orderline(this.get_last_orderline());
        },
        export_as_JSON: function () {
            var json = _super_order.export_as_JSON.apply(this, arguments);
            json.quotation_type = this.get_quotation_type();
            json.order_type = this.get_order_type();
            json.origin = this.get_origin();
            json.origin_ncf = this.get_origin_ncf();
            json.credit = this.get_credit();
            json.credit_ncf = this.get_credit_ncf();
            json.ncf = this.get_ncf();
            json.fiscal_type_name = this.get_fiscal_type_name();
            json.fiscal_type = this.get_fiscal_type();
            json.order_note = this.get_order_note();
            return json;
        },
        export_for_printing: function () {
            var json = _super_order.export_for_printing.apply(this, arguments);
            json.quotation_type = this.get_quotation_type();
            json.order_type = this.get_order_type();
            json.origin = this.get_origin();
            json.origin_ncf = this.get_origin_ncf();
            json.credit = this.get_credit();
            json.credit_ncf = this.get_credit_ncf();
            json.ncf = this.get_ncf();
            json.fiscal_type_name = this.get_fiscal_type_name();
            json.fiscal_type = this.get_fiscal_type();
            return json
        }
    });


});
