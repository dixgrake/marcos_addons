odoo.define('ipf_manager.devices', function (require) {

    var devices = require('point_of_sale.devices');
    var IpfApi = require('ipf_manager.service');
    var web_data = require('web.data');
    var Model = require('web.DataModel');
    var gui = require('point_of_sale.gui');
    var PopupWidget = require("point_of_sale.popups");

    devices.ProxyDevice.include({
        try_hard_to_connect: function (url, options) {
            var self = this;

            if (this.pos.config.iface_fiscal_printer) {
                options = options || {};

                self.set_connection_status('connecting');

                var url = self.pos.config.iface_fiscal_printer_host;

                function try_real_hard_to_connect(url, retries, done) {

                    done = done || new $.Deferred();

                    $.ajax({
                        url: url + "/state",
                        method: 'GET',
                        timeout: 1000
                    })
                        .done(function () {
                            done.resolve(url);
                        })
                        .fail(function () {
                            if (retries > 0) {
                                try_real_hard_to_connect(url, retries - 1, done);
                            } else {
                                done.reject();
                            }
                        });
                    return done;
                }

                return try_real_hard_to_connect(url, 3);


            } else {
                return this._super(url, options)
            }

        },
        connect: function (url) {
            var self = this;

            if (this.pos.config.iface_fiscal_printer) {
                var url = self.pos.config.iface_fiscal_printer_host;
                return $.ajax({type: "GET", url: url + "/software_version"})
                    .done(function (response) {
                        self.set_connection_status('connected');
                        localStorage.hw_proxy_url = url;
                        self.keepalive();
                    })
                    .fail(function (response) {
                        self.set_connection_status('disconnected');
                        console.error('Connection refused by the Proxy');
                    });

            } else {
                return this._super(url);
            }
        },
        keepalive: function () {
            var self = this;
            if (this.pos.config.iface_fiscal_printer) {
                function status() {
                    var url = self.pos.config.iface_fiscal_printer_host;
                    return $.ajax({type: "GET", url: url + "/state", timeout: 2500})
                        .done(function () {
                            var driver_status = {escpos: {status: "connected"}};
                            self.set_connection_status('connected', driver_status);
                        })
                        .fail(function () {
                            if (self.get('status').status !== 'connecting') {
                                self.set_connection_status('disconnected');
                            }
                        })
                        .always(function () {
                            setTimeout(status, 5000);
                        });
                }

                if (!this.keptalive) {
                    this.keptalive = true;
                    status();
                }

            } else {
                this._super();
            }

        },
        get_ipf_data: function (order_name) {
            var self = this;

            var order = self.pos.get_order();
            console.log(order);
            var ipfProxy = new IpfApi();

            var comments = $.trim(order.get_order_note() + " | " + self.pos.config.receipt_footer || '');
            var comments_list = comments.match(/.{1,40}/g);

            return new Model('pos.order').call("get_fiscal_data", [order_name]).then(function (result) {


                var ipf_invoice = {
                    type: result.fiscal_type,
                    copy: self.pos.config.iface_fiscal_printer_copy,
                    cashier: self.pos.user.id,
                    subsidiary: self.pos.config.iface_fiscal_printer_subsidiary[0],
                    ncf: result.ncf || "Documento de no venta",
                    reference_ncf: result.origin || "",
                    client: result.name,
                    rnc: result.rnc,
                    items: [],
                    payments: [],
                    discount: false,
                    charges: false,
                    comments: comments_list,
                    host: self.pos.config.iface_fiscal_printer_host,
                    invoice_id: result.id
                };


                order.orderlines.each(function (orderline) {
                    var line = orderline.export_as_JSON();
                    var product = self.pos.db.get_product_by_id(line.product_id);
                    var tax = orderline.get_taxes();

                    if (tax.length != 1) {
                        self.pos.gui.show_popup('error', {
                            'title': 'Error en el impuesto del producto',
                            'body': 'La impresora fiscal no admite productos con mas de un impuesto. [' + product.display_name + ']'
                        });
                        return
                    } else if (!$.inArray(tax, [0, 5, 8, 11, 13, 18])) {
                        self.pos.gui.show_popup('error', {
                            'title': 'Error en el impuesto del producto',
                            'body': 'Tiene un porciento de ITBIS no admitido. [' + product.display_name + ']'
                        });
                        return
                    } else {
                        var itbis = tax[0].amount
                    }

                    var nota = (typeof line.note === "undefined" ? "" : " " + line.note);
                    var description = $.trim(product.display_name + nota);
                    var description_list = description.match(/.{1,21}/g);

                    var ifp_line = {
                        description: description_list.pop(),
                        extra_descriptions: description_list,
                        quantity: line.qty,
                        price: line.price_unit || 0,
                        itbis: itbis,
                        discount: line.discount || false,
                        charges: false
                    };

                    ipf_invoice.items.push(ifp_line)

                });


                order.paymentlines.each(function (paymentline) {
                    var journal_type = paymentline.ipf_payment_type || "other";
                    var ipf_payment = {
                        type: journal_type,
                        amount: paymentline.amount,
                        description: false
                    };

                    ipf_invoice.payments.push(ipf_payment)
                });

                return ipf_invoice

            }).done(function (ipf_invoice) {
                var context = new web_data.CompoundContext({
                    active_model: "pos.order",
                    active_id: ipf_invoice.id
                });

                order.destroy();
                return ipfProxy.print_receipt(ipf_invoice, context);
            })

        },
        message: function (name, params) {
            var self = this;

            if (self.pos.config.iface_fiscal_printer) {
                var r = params.receipt;
            } else {
                var callbacks = this.notifications[name] || [];
                for (var i = 0; i < callbacks.length; i++) {
                    callbacks[i](params);
                }
            }
            if (this.get('status').status !== 'disconnected') {
                if (self.pos.config.iface_fiscal_printer) {
                    var parse_xml_params = $.parseXML(params.receipt);
                    var order_name = $(parse_xml_params).find("ipfordername").text();
                    return self.get_ipf_data(order_name);
                } else {
                    return this.connection.rpc('/hw_proxy/' + name, params || {});
                }
            } else {
                return (new $.Deferred()).reject();
            }
        },
        print_sale_details: function () {
            this.pos.gui.show_popup('ipfPrintReport');
        }
    });


    var IPFPrintReport = PopupWidget.extend({
        template: 'IPFPrintReport',

        events: _.extend({}, PopupWidget.prototype.events, {
            'click .ipf-cierre-z': 'ipf_cierre_z',
            'click .ipf-shift-change': 'ipf_shift_change',
            'click .ipf-report-x': 'ipf_report_x',
            'click .ipf-today-report': 'ipf_today_report',
            'click .ipf-shift-report': 'ipf_shift_report'
        }),
        ipf_cierre_z: function () {
            var self = this;
            var ipfProxy = new IpfApi();
            var context = new web_data.CompoundContext({
                active_model: "ipf.printer.config",
                active_id: self.pos.config.iface_fiscal_printer[0]
            });
            ipfProxy.get_z_close_print(context)
        },
        ipf_shift_change: function () {
            var self = this;
            var ipfProxy = new IpfApi();
            var context = new web_data.CompoundContext({
                active_model: "ipf.printer.config",
                active_id: self.pos.config.iface_fiscal_printer[0]
            });
            ipfProxy.get_new_shift_print(context)

        },
        ipf_report_x: function () {
            var self = this;
            var ipfProxy = new IpfApi();
            var context = new web_data.CompoundContext({
                active_model: "ipf.printer.config",
                active_id: self.pos.config.iface_fiscal_printer[0]
            });
            ipfProxy.get_x(context)

        },
        ipf_today_report: function () {
            var self = this;
            var ipfProxy = new IpfApi();
            var context = new web_data.CompoundContext({
                active_model: "ipf.printer.config",
                active_id: self.pos.config.iface_fiscal_printer[0]
            });
            ipfProxy.get_information_day(context)

        },
        ipf_shift_report: function () {
            var self = this;
            var ipfProxy = new IpfApi();
            var context = new web_data.CompoundContext({
                active_model: "ipf.printer.config",
                active_id: self.pos.config.iface_fiscal_printer[0]
            });
            ipfProxy.get_information_shift(context)
        }
    });

    gui.define_popup({name: 'ipfPrintReport', widget: IPFPrintReport});

});
