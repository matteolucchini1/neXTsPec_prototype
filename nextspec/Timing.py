import numpy as np
import os
import scipy
import pyfftw
from pyfftw.interfaces.numpy_fft import (
    fft,
    fftfreq,
)

import matplotlib.pyplot as plt
import matplotlib.pylab as pl
from matplotlib import rc, rcParams
rc('text',usetex=True)
rc('font',**{'family':'serif','serif':['Computer Modern']})
fi = 22
plt.rcParams.update({'font.size': fi-5})

colorscale = pl.cm.PuRd(np.linspace(0.,1.,5))

from Operator import nDspecOperator

class FourierProduct(nDspecOperator):
    """
    Parent class for all Fourier operators in the software. It is mainly used 
    to handle performing Fourier transforms from the time to the frequency 
    domain, which is implemented using two methods.
    The first simply uses the numpy fftw to calculate a standard fast Fourier 
    transform; the second uses the sinc function decomposition described in 
    Uttley and Malzac 2023 (arXiv:2312.08302), eq. 27. 
    Depending on the input provided to the constructor, the class can switch 
    automatically between the two implementations to ensure the Fourier 
    transform calculation is correct.
    
    Parameters 
    ----------  
    time_array: np.array
        The array of times over which the quantity to be transformed is defined.
        If using the fft method, this array also defines the frequencies over
        which the transform is computed. 
    
    freq_array: np.array 
        Defines the range of Fourier frequencies over which the input quantity 
        is to be transformed, only if using the sinc function method. Has no 
        effect with fft.
    
    method: {"fft" | "sinc" }
        The computational method to calculate the Fourier tranform of input 
        quantities. Options are "fft", for a standard Fast Fourier Transform 
        as implemented by numpy.fft, and "sinc", for the sinc function 
        decomposition described in Uttley and Malzac 2023 (arXiv:2312.08302).
    
    Attributes 
    ----------  
    times: np.array 
        The array of times over which quantities are to be Fourier transformed.
        Necessary to utilize the sinc transform method. This array needs to be 
        linearly spaced to use the fft method; if this is not the case, the 
        class defaults to the sinc method. 
    
    time_bins: np.array 
        The array of widths of each bin in the "time" array. The FFT method can 
        only be called if all the elements of the array are equal to the first, 
        or in other words if the "time" array is linearly spaced.    
    
    n_times: int 
        The size of the "times" and "time_bins" arrays.
    
    method:  {"fft" | "sinc" }
        The computational method to calculate the Fourier tranform of input 
        quantities. Options are "fft", for a standard Fast Fourier Transform 
        as implemented by numpy.fft, and "sinc", for the sinc function 
        decomposition described in Uttley and Malzac 2023 (arXiv:2312.08302).
    
    freqs: np.array
        The array of Fourier frequencies over which the Fourier transform is 
        computed. When using the "fft" method, this is derived from the "times"
        array, considering only the positive frequency bins. When using the 
        "sinc" method, this is set by the user when the operator object is first
        initialized. 
    
    n_freqs: int
        The size of the "freqs" array.   
        
    irf_sinc_arr: np.array
        A matrix of size (n_freqs) times n_times, which stores how each time bin
        in the "times" array maps to a given sinc function with frequency given 
        in the "freqs" array. This is required for use of the sinc method, and 
        therefore is updated automatically every time the user changes frequency
        grid.       
    """

    def __init__(self,time_array,freq_array=0,method='fft'):

        self.times = time_array
        self.time_bins = np.diff(self.times)
        self.n_times = self.times.size
        
        if np.all(np.isclose(self.time_bins, self.time_bins[0])) == False:
            self.method('sinc')
        elif np.isin(method,(['sinc'],['fft'])) == True:
            self.method(method)
        else:
            self.method('fft')
        #if we're going to do fft the array is pre-determined, otherwise it should be in the arguments
        
        #add safeguard for sinc method with freq array undefined
        self.freqs = self._set_frequencies(freq_array)     
        
        pass
       
    def _set_frequencies(self,freq_array=0,rebin=False):
        """   
        This method is used to the internal frequency array and its size. If 
        using the sinc transform method, the decomposition matrix irc_sinc_arr 
        is also updated automatically.
        
        Parameters
        ----------
        freq_array: np.array 
            If using the sinc method, this is the array that will be used as the
            objet Fourier frequency grid. If using the fft method, the array is
            computed from the "n_times" and "time_bins" attributes, and is 
            linearly spaced in Fourier frequency, unless the "rebin" flag is 
            true (see below).
            
        rebin: bool
            Used only for the fft method. If false, the method assumes we are 
            initializing the object for the first time, and therefore sets the 
            frequency grid to the output of the fftfreq function. If true, it 
            means we want to switch from the linear frequency grid provided by
            fftfreq to some other user-specified grid through the appropriate 
            methods of each object.

        Returns
        -------
        frequencies: np.array 
            The updated frequency array, which can then be assigned to the
            "freqs" method. 
            
        """
        if (self.method == 'fft'):
            if (rebin == True):
                frequencies = freq_array
            else:
                fgt0 = self._positive_fft_bins()
                frequencies = fftfreq(self.n_times,self.time_bins[0])[fgt0]
            self.n_freqs = len(frequencies)
        #tbd: improve errors/catch for weird input of frequencies
        elif (self.method == 'sinc'):
            if np.shape(freq_array) == () or len(np.shape(freq_array)) > 1:
                raise TypeError("Input frequency grid in incorrect format")     
            self.n_freqs = len(freq_array)
            frequencies = freq_array
            self.irf_sinc_arr = self._sinc_decomp()
        else:
            raise ValueError("Fourier transform method not recognized")
        
        return frequencies
   
    def _compute_fft(self,input_array):
        """   
        This method computes the fast Fourier transform of the input array.
        
        Parameters
        ----------
        input_array: np.array 
            The array to be Fourier transformed. 

        Returns
        ------
        transform: np.array 
            The Fourier transform of the input array, including only the values 
            defined at positive, non-zero frequency bins. 
        """        
        fgt0 = self._positive_fft_bins()
        transform = fft(input_array)[fgt0]        
        
        return transform

    def _positive_fft_bins(self,include_zero=False):
        """
        This method return the range of positive frequencies of a complex FFT 
        and discards the negative ones.
        This function is copied from the Stingray library 
        (https://docs.stingray.science/en/v1.1.2.4/)_ 
    
        This assumes we are using Numpy's FFT, or something compatible
        with it, like ``pyfftw.interfaces.numpy_fft``, where the positive
        frequencies come before the negative ones, the Nyquist frequency is
        included in the negative frequencies but only in even number of bins,
        and so on.
        This is mostly to avoid using the ``freq > 0`` mask, which is
        memory-hungry and inefficient with large arrays. We use instead a
        slice object, giving the range of bins of the positive frequencies.
    
        See https://numpy.org/doc/stable/reference/
                    routines.fft.html#implementation-details
    
        Parameters
        ----------
        include_zero : bool, default False
            Include the zero frequency in the output slice.
    
        Returns
        -------
        positive_bins : `slice`
            Slice object encoding the positive frequency bins.
        """
        # The zeroth bin is 0 Hz. We usually don't include it, but
        # if the user wants it, we do.
        minbin = 1
        if include_zero:
            minbin = 0            
        
        if self.n_times % 2 == 0:
            return slice(minbin, self.n_times // 2)                
        
        return slice(minbin, (self.n_times + 1) // 2)

    def _sinc_decomp(self):
        """   
        This method calculates the mapping between time delay bins and Fourier  
        frequency when using the sinc decomposition method, following eq. 27 in  
        Uttley and Malzac (https://arxiv.org/abs/2312.08302).
        
        Returns
        -------
        decomp: np.array 
            A two-d array of size (n-times x n_freqs), containing the 
            mapping of time delay bins to Fourier frequency. This is the
            same the term delta_tau * sinc(delta_tau*nu) * exp(-i 2 pi nu tau) 
            in Malzac and Uttley.
        
        """
        deltau = np.zeros(len(self.times))
        deltau[0] = self.times[0]
        deltau[1:len(self.times)] = self.time_bins
        #all the reshaping here is to ensure that decomp is the correct 
        #format - ie, a matrix of size (n_times x n_freqs)
        decomp = np.sinc(deltau.reshape((len(deltau),1))*
                         self.freqs.reshape((1,self.n_freqs)))*
                         np.exp(-2*np.pi*self.freqs.reshape((1,self.n_freqs))*
                         self.times.reshape((len(deltau),1))*1j)
         
         return decomp 
    
    def _compute_sinc(self,input_array):
        """   
        This method computes the Fourier transform of the array using the sinc 
        decomposition method, which can be more computationally efficient than 
        fft in some cases. 
        
        Parameters
        ----------
        input_array: np.array 
            The array to be Fourier transformed. 

        Returns
        ------
        transform: np.array 
            The Fourier transform of the input array for the set of time delay 
            and Fourier frequency bins set by _sinc_decomp(). 
        """
        #tbd: add safeguard to check that the sinc decomp is defined
        transform = np.matmul(input_array,self.irf_sinc_arr)        
        
        return transform
        
    def transform(self,input_array):
        """   
        This method acts like a wrapper to Fourier transform array, and calls 
        the appropriate method depending on user settings. 
        
        Parameters
        ----------
        input_array: np.array 
            The array to be Fourier transformed. 

        Returns
        ------
        transform: np.array 
            The Fourier transform of the input array.
        """        
        if (self.method == 'fft'):
            transform = self._compute_fft(input_array)
        elif (self.method == 'sinc'):
            transform = self._compute_sinc(input_array)
        else:
            raise ValueError("Fourier transform method not recognized")
        
        return transform 

    
class PowerSpectrum(FourierProduct):
    """    
    This class computes model power spectra from a given signal input. The 
    public methods in the class call those in nDspecOperator and FourierProduct  
    nas ecessary to Fourier transform input quantities and handle changes to the
    internal frequency grid. 
    
    Parameters inherited from FourierProduct
    ----------  
    time_array: np.array
        The array of times over which the input signal is defined. 
    
    freq_array: np.array 
        The Fourier frequency array over which the power spectrum is defined. 
    
    method: {"fft" | "sinc" }
        The computational method to calculate the power spectrum. Options are 
        "fft", for a standard Fast Fourier Transform  as implemented by 
        numpy.fft, and "sinc", for the sinc function decomposition described in 
        Uttley and Malzac 2023 (arXiv:2312.08302).
     
    Attributes inherited from FourierProduct  
    ----------  
    times: np.array 
        The array of times over which the input signal is defined. 
    
    time_bins: np.array 
        The array of widths of each bin in the "time" array. The FFT method can 
        only be used if all the elements of the array are equal to the first,
        or in other words if the "time" array is linearly spaced.
    
    n_times: int 
        The size of the "times" and "time_bins" arrays.
    
    method:  {"fft" | "sinc" }
        The computational method to calculate the Fourier tranform of input 
        quantities. Options are "fft", for a standard Fast Fourier Transform 
        as implemented by numpy.fft, and "sinc", for the sinc function 
        decomposition described in Uttley and Malzac 2023 (arXiv:2312.08302).
    
    freqs: np.array
        The array of Fourier frequencies over which the power spectrum is 
        defined and/or computed.
    
    n_freqs: int
        The size of the "freqs" array.   
        
    irf_sinc_arr: np.array
        A matrix of size (n_freqs x n_times), which stores how each time bin in 
        the "times" array maps to a given sinc function with frequency given in
        the "freqs" array. This is required for use of the sinc method, and 
        therefore is updated automatically every time the user changes frequency
        grid.  
        
    Other Attributes 
    ----------   
    power_spec: np.array 
        An array of size(n_freqs), storing the un-normalized power spectrum of an
        input signal.     
    """
    
    def __init__(self,time_array,freq_array=0,method='fft'):
        FourierProduct.__init__(self,time_array,freq_array,method)        
        pass 

    def compute_psd(self,signal):
        """   
        This method calculates the power spectrum, defined over the class 
        "freqs" Fourier frequency array, of an input array.
        
        Parameters
        ----------
        signal: np.array 
            The quantity from which to calculate the power spectrum.        

        Returns
        -------
        self: nDspec.PowerSpectrum 
            The same class instance after calculating the power spectrum.
        """
        transform = self.transform(signal)
        self.power_spec = np.multiply(transform,np.conj(transform))        
        
        return

    def rebin_frequency(self,new_grid):
        """   
        This methods rebins the class freqs array, and also updates all relevant 
        attributes (n_freqs, power_spec). The re-binned power spectrum is 
        calculated by interpolating the previous power over the new grid. 
        
        Parameters
        ----------
        new_grid: np.array 
            The new grid of Fourier frequencies over which to rebin the power 
            spectrum.  

        Returns
        -------
        self: nDspec.PowerSpectrum 
            The same class instance after updating the Fourier frequency array
            and rebinning the power spectrum.       
        """
        new_power = self._interpolate(self.power_spec,self.freqs,new_grid)
        self.freqs = self._set_frequencies(new_grid)
        self.power_spec = new_power        
        
        return 
    
    def plot_psd(self,units='Power*freq'):
        """ 
        This method plots the either the power or power per unit frequency 
        as a function of frequency, stored in the class instance.  
        
        Parameters
        ----------
        units: string 
            Sets the units to plot on the y axis - the default "power*freq" 
            displays the power at that frequency, "power" instead uses the power
            per unit frequency.  

        """
        fig, ((ax1)) = plt.subplots(1,1,figsize=(9.,6.))   
        
        if units == 'Power':
            ax1.plot(self.freqs,self.power_spec)
            ax1.set_ylabel("Power")
        elif units == "Power*freq":
            ax1.plot(self.freqs,self.power_spec*self.freqs)
            ax1.set_ylabel("Power*frequency")
        else:
            raise ValueError("Y axis units not recognized")
        
        ax1.set_xscale("log",base=10)
        ax1.set_yscale("log",base=10)
        ax1.set_xlabel("Frequency")  
        
        plt.tight_layout()
        plt.show()        
        
        return
        
        
class CrossSpectrum(FourierProduct):
    """    
    This class computes model cross spectra from a given input, assumed to be 
    either a user-provided impulse response function or a user-provided model 
    (such as a transfer function) already defined in Fourier space. It can 
    handle both one-dimensional, frequency dependent cross spectra between just 
    two energy bands, or two-dimensional cross spectra defined over multiple 
    energy and frequency grids. 
    
    Parameters inherited from FourierProduct
    ----------  
    time_array: np.array
        The array of times over which the input signal is defined. 
    
    freq_array: np.array 
        The Fourier frequency array over which the power spectrum is defined. 
    
    method: {"fft" | "sinc" }
        The computational method to calculate the cross spectrum. Options are 
        "fft", for a standard Fast Fourier Transform  as implemented by 
        numpy.fft, and "sinc", for the sinc function decomposition described in 
        Uttley and Malzac 2023 (arXiv:2312.08302).    


    Other parameters 
    ----------  
    energ: np.array 
        The array of energy (or energy channels) bin mid-points over which a
        two-dimensional cross spectrum is defined. If we are only considering 
        the cross-spectrum between two energy bands, this defaults to "None". 

    Attributes inherited from FourierProduct  
    ----------  
    times: np.array 
        The array of times over which the input signal is defined. 
    
    time_bins: np.array 
        The array of widths of each bin in the "time" array. The FFT method can 
        only be used if all the elements of the array are equal to the first,
        or in other words if the "time" array is linearly spaced.
    
    n_times: int 
        The size of the "times" and "time_bins" arrays.
    
    method:  {"fft" | "sinc" }
        The computational method to calculate the Fourier tranform of input 
        quantities. Options are "fft", for a standard Fast Fourier Transform 
        as implemented by numpy.fft, and "sinc", for the sinc function 
        decomposition described in Uttley and Malzac 2023 (arXiv:2312.08302).
    
    freqs: np.array
        The array of Fourier frequencies over which the power spectrum is 
        defined and/or computed.
    
    n_freqs: int
        The size of the "freqs" array.   
        
    irf_sinc_arr: np.array
        A matrix of size (n_freqs x n_times), which stores how each time bin in 
        the "times" array maps to a given sinc function with frequency given in
        the "freqs" array. This is required for use of the sinc method, and 
        therefore is updated automatically every time the user changes frequency
        grid.  
    
    Other attributes 
    ---------- 
    n_chan: int 
        The size of the "energy" array. Defaults to 1 for a one-dimensional 
        cross spectrum between two energy bands. 
    
    chans: np.array 
        An array containing the indexes of each energy bin (or channel) in the 
        cross spectrum. Defaults to 0 for a one-dimensional cross spectrum 
        between two energy bands.  
    
    power_spec: np.array 
        A one-dimensional array of size (n_freq) containing the assumed shape 
        of the power spectrum. This is necessary to a) calculate the cross 
        product from an impulse response and b) calculate Fourier frequency 
        averaged products like lag-energy spectra in a given frequency range. 
    
    imp_resp: np.array 
        An array of size (n_chan x n_times), storing the model impulse 
        response function from which to compute the cross spectrum. 
    
    ref: np.array 
        An array of size (n_times), storing the reference band signal. The 
        reference band can either be computed directly from the imp_resp 
        attribute, using the set_reference_idx method, or it can be provided 
        by the user, using the set_reference_lc method. 
    
    trans_func: np.array 
        An array of size (n_chan x n_freq), containing the Fourier transform of 
        each channel of the impulse response function provided by the user - 
        formally, this is the transfer function. It is used together with the 
        weighing power spectrum power_spec to calculate the cross spectrum, and 
        is necessary to compute one-dimensional frequency-dependent products 
        (such as lag-frequency spectra) from a two-dimensional cross spectrum. 
        If users are not providing an impulse response function, this attribute 
        can be set by hand (e.g. from a model defined in Fourier space).

    cross: np.array  
        An array of size (n_chan x n_freq) containing the full (one or two 
        dimensional) cross spectrum, defined as the cross product between the
        Fourier transforms of one or more channels of interest and of the 
        reference band, and weighed by the power spectrum. 
        If users are not providing an impulse response or transfer function, 
        this attribute can be set by hand (e.g. from a model defined in Fourier 
        space).     
    """
    #in the constructor we assume at minumum one channel of interest
    #the FourierProduct constructor sorts out the sinc decomp if we choose that method
    #check on energies to not be stupid/array sizes to be correct
    #if no channels provided assume it's 1d
    def __init__(self,time_array,freq_array=0,energ=None,method='fft'):
         FourierProduct.__init__(self,time_array,freq_array,method)
        self.energ = energ
        if energ is None:
            self.n_chan = 1
            self.chans = 0
        else:
            self.n_chan = len(self.energ)
            self.chans = np.linspace(0,self.n_chan-1,self.n_chan,dtype=np.int16)  
        pass      

    def set_psd_weights(self,input_power):
        """  
        This method sets the weighing power spectrum power_spec from a given 
        input.  
        
        Parameters
        ----------
        input_power: np.array 
            An array of size (n_freqs) that is to be used as the weighing power 
            spectrum when computing the cross spectrum.
        """
        #tbd - something that checks that the psd is defined on the right frequency ig?
        if (len(input_power)) != self.n_freqs:
            raise ValueError("PSD array is the incorrect size!")        
        self.power_spec = input_power
        
        return

    def set_impulse(self,signal):
        """   
        This method sets the impulse response function imp_resp from which the 
        cross spectrum is calculated.
        
        Parameters
        ----------
        signal: np.array 
            An array of size (n_chan x n_times) containing the model impulse 
            response function. 
        """
        #tbd: add thing that checks the arrays are the right size
        self.imp_resp = signal
        #ensure the correct irf input format for a 1d cross spectrum        
        if self.n_chan == 1:
            self.imp_resp = np.reshape(self.imp_resp,(1,self.n_times))
        
        return

    def set_reference_idx(self,chans):
        """   
        This method sets the reference band from a list of channel indexes 
        provided by the user. Currently, it is up to users to convert a given 
        energy range they might be interested in into these channel indexes, 
        pending improvements to the Operator class.
        
        Parameters
        ----------
        chans: np.array 
            An array of integers of size <= (n_chan) containing the indexes 
            of the channels (to be compared with the chans attribute), from 
            which to compute the reference band. 

        """   
        ref_index = np.searchsorted(chans,self.chans)
        self.ref = np.reshape(np.sum(impulse_test[ref_index,:],axis=0),
                             (self.n_times))
        
        return

    def set_reference_lc(self,input_lc):
        """   
        This method sets the reference band from an array (e.g. count rate as a
        function of energy) provided by the user.
        
        Parameters
        ----------
        input_lc: np.array 
            An arrray of size (n_chan) containing the reference band lightcurve.
        """
        if (len(input_lc)) != self.times.size:
            raise ValueError("Reference array is the incorrect size!")
        
        self.ref = input_lc
        
        return
    
    def compute_cross(self,signal=None,reference=None,power=None):
        """   
        This method computes the transfer function and cross spectrum from the 
        impulse response, reference band, and power spectra provided by the 
        user. These can either be already stored by the setter methods 
        set_psd_weights, set_impulse, and set_reference_idx or set_reference_lc
        (which is the default behavior), or they can be passed as arguments of 
        this method. In the latter case, the reference can only be provided in 
        array, rather than channel index, form.
        
        Parameters
        ----------
        signal: np.array 
            An array of size (n_chan x n_times) containing the model impulse 
            response function. 
            
        reference: np.array 
            An arrray of size (n_chan) containing the reference band lightcurve.
            
        power: np.array 
            An array of size (n_freqs) that is to be used as the weighing power 
            spectrum when computing the cross spectrum.
        """
        if signal is None:
            signal = self.imp_resp
        else:
            self.set_impulse(signal)
        
        if reference is None:
            reference = self.ref
        else:
            self.set_reference_lc(reference)
        
        if power is None:
            power_spec = self.power_spec 
        else:
            self.set_psd_weights(power)
        
        self.cross = []
        self.trans_func = []
        
        ref_ft = self.transform(reference)  
        for index in range(self.n_chan):
            ci_ft = self.transform(signal[index,:])
            self.trans_func.append(ci_ft)
            cross_prod = power_spec*np.multiply(ci_ft,np.conj(ref_ft))
            self.cross.append(cross_prod)                 

        self.cross = np.reshape(np.array(self.cross),
                               (self.n_chan,self.n_freqs))
        self.trans_func = np.reshape(np.array(self.trans_func),
                                    (self.n_chan,self.n_freqs))
        
        return

    def rebin_frequency(self,new_grid):
        """   
        This method rebins the cross spectrum and transfer function stored in 
        the object to a new frequency grid, and updates the relevant class 
        attributes as necessary.
        
        Parameters
        ----------
        new_grid: np.array 
            An array of arbitrary size, containing the Fourier frequency bin 
            midpoints of the new grid.
        """        
        new_cross = []
        new_trans = []
        new_power = self._interpolate(self.power_spec,self.freqs,new_grid)
        
        for index in range(self.n_chan):
            cross_rebin = self._interpolate(self.cross[index,:],
                                            self.freqs,new_grid)
            trans_rebin = self._interpolate(self.trans[index,:],
                                            self.freqs,new_grid)
            new_cross.append(cross_rebin)
            new_trans.append(trans_rebin)
        
        self.freqs = self._set_frequencies(new_grid)
        self.power_spec = new_power
        self.cross = np.reshape(np.array(new_cross),(self.n_chan,self.n_freqs))
        self.trans = np.reshape(np.array(new_trans),(self.n_chan,self.n_freqs)) 
        
        return
    
    def real(self):
        """   
        This method returns the real part of the cross spectrum, both for one 
        and two dimensional cases.

        Returns
        -------
        real: np.array 
            An array of real parts of the cross spectrum, of size 
            (n_chan x n_freq)
        """
        real = np.real(self.cross)
        
        return real

    def imag(self):
        """   
        This method returns the imaginary part of the cross spectrum, both for  
        one and two dimensional cases.

        Returns
        -------
        imag: np.array 
            An array of imaginary parts of the cross spectrum, of size 
            (n_chan x n_freq)
        """
        imag = np.imag(self.cross)
        
        return imag

    def mod(self):
        """   
        This method returns the modulus of the cross spectrum, both for one and
        and two dimensional cases.

        Returns
        -------
        mod: np.array 
            An array of moduli of the cross spectrum, of size (n_chan x n_freq)
        """
        mod = np.absolute(self.cross)
        
        return mod 

    def phase(self):
        """   
        This method returns the phase of the cross spectrum, both for one and
        and two dimensional cases.

        Returns
        -------
        phases: np.array 
            An array of phases of the cross spectrum, of size (n_chan x n_freq)
        """
        phase = np.angle(self.cross)
        
        return phase

    def lag(self):
        """   
        This method converts the phase of the cross spectrum, both for one and
        and two dimensional cases, into time lags.

        Returns
        -------
        lags: np.array 
            An array of phases of the cross spectrum, of size (n_chan x n_freq)
        """
        lag_conv = 2.*np.pi*self.freqs
        lags = self.phase()/lag_conv
        
        return lags 

    def _oned_cross(self,int_bounds,ref_bounds=None):
        """   
        This method converts a two-dimensional transfer function stored in the 
        "trans" attribute into a one-dimensional, Fourier frequency dependent  
        cross spectrum, by summing over energy channels specified by the user  
        and re-calculating the cross product between the reference band and 
        channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        cross: np.array 
            A one-dimensional array of size (n_freq) containing the one 
            dimensional cross spectrum between the channels of interest and the 
            reference band provided by the user. 
        """
        #by default use the same reference band as the full 2d cross
        #the reason the reference band is treated differently is that if we want to 
        #use the reference band we already passed, the signal is already summed over all
        #energy channels before Fourier transforming. If instead we want to use some other
        #referene band, it is more convenient to just sum over the (pre calculated) transfer
        #function. 
        if ref_bounds is None:
            ref = self.transform(self.ref)
        else:
            idx_ref = np.where(np.logical_and(self.energ>ref_bounds[0],self.energ<ref_bounds[1]))
            ref = np.sum(self.trans_func[idx_ref,:],axis=1)
        
        idx_int = np.where(np.logical_and(self.energ>int_bounds[0],self.energ<int_bounds[1]))
        int = np.sum(self.trans_func[idx_int,:],axis=1)
        cross = self.power_spec*np.multiply(int,np.conj(ref))
        
        return cross

    def real_frequency(self,int_bounds,ref_bounds=None):
        """   
        This method computes, from a two-dimensional transfer function stored in  
        the "trans" attribute, the real part of a one-dimensional, Fourier 
        frequency dependent cross spectrum, by summing over energy channels 
        specified by the user and re-calculating the cross product between the 
        reference band and channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        real_spectrum: np.array 
            A one-dimensional array of size (n_freq) containing the real part of
            the one dimensional cross spectrum between the channels of interest 
            and the reference band provided by the user, as a function of 
            Fourier frequency.
        """
        real_spectrum = np.real(self._oned_cross(int_bounds,ref_bounds))
        real_spectrum = np.reshape(real_spectrum,self.n_freqs)
        
        return real_spectrum
    
    def imag_frequency(self,int_bounds,ref_bounds=None):
        """   
        This method computes, from a two-dimensional transfer function stored in  
        the "trans" attribute, the imaginary part of a one-dimensional, Fourier 
        frequency dependent cross spectrum, by summing over energy channels 
        specified by the user and re-calculating the cross product between the 
        reference band and channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        imag_spectrum: np.array 
            A one-dimensional array of size (n_freq) containing the imaginary 
            part of the one dimensional cross spectrum between the channels of  
            interest and the  reference band provided by the user, as a function 
            of Fourier frequency. 
        """
        imag_spectrum = np.imag(self._oned_cross(int_bounds,ref_bounds))
        imag_spectrum = np.reshape(imag_spectrum,self.n_freqs)
        
        return imag_spectrum
    
    def mod_frequency(self,int_bounds,ref_bounds=None):
        """   
        This method computes, from a two-dimensional transfer function stored in  
        the "trans" attribute, the modulus of a one-dimensional, Fourier 
        frequency dependent cross spectrum, by summing over energy channels 
        specified by the user and re-calculating the cross product between the 
        reference band and channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        mod_spectrum: np.array 
            A one-dimensional array of size (n_freq) containing the modulus 
            of the one dimensional cross spectrum between the channels of  
            interest and the  reference band provided by the user. 
        """
        mod_spectrum = np.absolute(self._oned_cross(int_bounds,ref_bounds))
        mod_spectrum = np.reshape(mod_spectrum,self.n_freqs)
        
        return mod_spectrum
    
    def phase_frequency(self,int_bounds,ref_bounds=None):
        """   
        This method computes, from a two-dimensional transfer function stored in  
        the "trans" attribute, the phase of a one-dimensional, Fourier frequency 
        dependent cross spectrum, by summing over energy channels specified
        by the user and re-calculating the cross product between the reference
        band and channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        phase_spectrum: np.array 
            A one-dimensional array of size (n_freq) containing the phase 
            one dimensional cross spectrum between the channels of  
            interest and the  reference band provided by the user, as a function 
            of Fourier frequency. 
        """
        phase_spectrum = np.angle(self._oned_cross(int_bounds,ref_bounds))
        phase_spectrum = np.reshape(phase_spectrum,self.n_freqs)
        
        return phase_spectrum
    
    def lag_frequency(self,int_bounds,ref_bounds=None):        
        """   
        This method computes, from a two-dimensional transfer function stored in  
        the "trans" attribute, the time lags of a one-dimensional, Fourier  
        frequency dependent cross spectrum, by summing over energy channels 
        specified by the user and re-calculating the cross product between the 
        reference band and channels of interest.
        
        Parameters
        ----------
        int_bounds: np.array 
            A list of integer indexes for the energy channels to be used in the 
            channels of interest - using the convention used in X-ray spectral 
            timing, this should be the energy band where reverberation lags 
            appear with negative values.
            
        ref_bounds: np.array  
            A list of integer indexes for the energy channels to be used in the 
            reference band. By default, this assumes that the reference band is 
            identical to that used in calculating the cross spectrum. 

        Returns
        -------
        mod_spectrum: np.array 
            A one-dimensional array of size (n_freq) containing the time lags 
            of the one dimensional cross spectrum between the channels of  
            interest and the reference band provided by the user, as a function 
            of Fourier frequency.  
        """
        lag_spectrum = self.phase_frequency(int_bounds,ref_bounds)/
                       (2.*np.pi*self.freqs)
               
        return lag_spectrum
    
    def real_energy(self,nu_min,nu_max):
        """ 
        This method computes the real part of a one-dimensional cross spectrum 
        as a function of energy, by averaging the attribute "cross" over a given
        frequency range specified by the user. 
        
        Parameters
        ----------
        nu_min: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        nu_max: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        Returns
        -------
        real_sectrum: np.array 
            An array of size (n_chan) containing the real part of the Fourier 
            frequency averaged cross spectrum, as a function of energy. 
        """
        integrated_resp = self._integrate_range(self.cross,self.freqs,
                                                nu_min,nu_max,axis=1)
        real_spectrum = np.real(integrated_resp/(nu_max-nu_min))
        real_spectrum = np.reshape(real_spectrum,self.n_chan)
        
        return real_spectrum

    def imag_energy(self,nu_min,nu_max):
        """ 
        This method computes the imaginary part of a one-dimensional cross  
        spectrum as a function of energy, by averaging the attribute "cross" 
        over a given frequency range specified by the user. 
        
        Parameters
        ----------
        nu_min: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        nu_max: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        Returns
        -------
        imag_spectrum: np.array 
            An array of size (n_chan) containing the imaginary part of the  
            Fourier frequency averaged cross spectrum, as a function of energy. 
        """
        integrated_resp = self._integrate_range(self.cross,self.freqs,
                                                nu_min,nu_max,axis=1)
        imag_spectrum = np.imag(integrated_resp/(nu_max-nu_min))
        imag_spectrum = np.reshape(imag_spectrum,self.n_chan)
        
        return imag_spectrum
    
    def mod_energy(self,nu_min,nu_max):
        """ 
        This method computes the modulus of a one-dimensional cross spectrum as 
        a function of energy, by averaging the attribute "cross" over a given 
        frequency range specified by the user. 
        
        Parameters
        ----------
        nu_min: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        nu_max: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        Returns
        -------
        mod_spectrum: np.array 
            An array of size (n_chan) containing the modulus of the Fourier
            frequency averaged cross spectrum, as a function of energy. 
        """
        integrated_resp = self._integrate_range(self.cross,self.freqs,
                                                nu_min,nu_max,axis=1)
        mod_spectrum = np.absolute(integrated_resp/(nu_max-nu_min))
        mod_spectrum = np.reshape(mod_spectrum,self.n_chan)
        
        return mod_spectrum
    
    def phase_energy(self,nu_min,nu_max):
        """ 
        This method computes the phase of a one-dimensional cross spectrum
        as a function of energy, by averaging the attribute "cross" over a given
        frequency range specified by the user. 
        
        Parameters
        ----------
        nu_min: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        nu_max: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        Returns
        -------
        phase_spectrum: np.array 
            An array of size (n_chan) containing the phase of the Fourier
            frequency averaged cross spectrum, as a function of energy. 
        """
        integrated_resp = self._integrate_range(self.cross,self.freqs,
                                                nu_min,nu_max,axis=1)
        phase_spectrum = np.angle(integrated_resp/(nu_max-nu_min))
        phase_spectrum = np.reshape(phase_spectrum,self.n_chan)
        
        return phase_spectrum
    
    def lag_energy(self,nu_min,nu_max):
        """ 
        This method computes the time lags of a one-dimensional cross spectrum
        as a function of energy, by averaging the attribute "cross" over a given
        frequency range specified by the user. 
        
        Parameters
        ----------
        nu_min: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        nu_max: np.float 
            The lower bound of Fourier frequency over which to average the two 
            dimensinoal cross spectrum
            
        Returns
        -------
        lag_spectrum: np.array 
            An array of size (n_chan) containing the time lags of the Fourier
            frequency averaged cross spectrum, as a function of energy. 
        """
        lag_spectrum = self.phase_energy(nu_min,nu_max)/
                       (2.*np.pi*(nu_max-nu_min))
        
        return lag_spectrum
        

    #tbd: add setting to return the ax objects instead so I can combine plots
    def plot_cross_1d(self,form="polar"):
        """   
        This method plots the a one-dimensional cross spectrum as a function of  
        Fourier frequency.
        
        Parameters
        ----------
        form: string 
            A qualifier to choose in which units to plot the cross spectrum. 
            By default, form="polar" will plot the modulus, phase, and lag 
            frequency spectrum. Alternatively, form="cartesian" plots the real 
            and imaginary parts of the cross spectrum.
        """
        #same as power spectrum, double check plotting style
        if form == "cartesian":
            fig, ((ax1,ax2)) = plt.subplots(1,2,figsize=(10.,5.))   
            
            ax1.plot(self.freqs,np.transpose(self.real()))
            ax1.set_xscale("log",base=10)
            ax1.set_ylabel("Real")
            ax1.set_xlabel("Frequency")  
            
            ax2.plot(self.freqs,np.transpose(self.imag()))
            ax2.set_xscale("log",base=10)
            ax2.set_ylabel("Imaginary")
            ax2.set_xlabel("Frequency")
            
            plt.tight_layout()
            plt.show()
        elif form == "polar":
            zero_line = np.zeros(self.n_freqs)
            #tbd: sort out the limits for the lag plot
            phase_wrap = 1/(2.*self.freqs)   
            
            fig, ((ax1,ax2,ax3)) = plt.subplots(1,3,figsize=(15.,5.))
            
            ax1.plot(self.freqs,np.transpose(self.mod()))
            ax1.set_xscale("log",base=10)
            ax1.set_yscale("log",base=10)
            ax1.set_xlabel("Frequency")
            ax1.set_ylabel("Modulus")    
            
            ax2.plot(self.freqs,np.transpose(self.phase()))
            ax2.plot(self.freqs,zero_line,linestyle='dotted',color='black')
            ax2.set_xscale("log",base=10)
            ax2.set_ylabel("Phase")
            ax2.set_xlabel("Frequency") 

            lag_min = np.min(np.transpose(self.lag()))
            lag_max = np.max(np.transpose(self.lag()))
            
            ax3.plot(self.freqs,zero_line,linestyle='dotted',color='black')
            ax3.plot(self.freqs,np.transpose(self.lag()))
            ax3.plot(self.freqs,phase_wrap,
                     linestyle='dotted',color='tab:orange')
            ax3.plot(self.freqs,-phase_wrap,
                     linestyle='dotted',color='tab:orange')
            ax3.set_xscale("log",base=10)
            ax3.set_ylabel("Time")
            ax3.set_xlabel("Frequency")
            ax3.set_ylim([min(0,lag_min)-0.05*lag_max,
                          max(0,lag_max)+0.05*lag_min])
            
            plt.tight_layout()
            plt.show()
        else:
            raise ValueError("plot format not supported")
        return

    def _plot_limits(self,plot_input):
        """   
        This method computes the normalization and ticks for two-dimensional 
        plots of the cross spectrum. 
        
        Parameters
        ----------
        plot_input: np.array 
            The two-dimensional array to be plotted, from which to define the 
            axis limits for the plots.

        Returns
        -------
        norm: np.float 
            The normalization to be used for the colorbar in the plot. 
            
        ticks: np.array 
            The list of ticks to show on the colorbar. 
        """
        lim_min = np.min(plot_input)
        lim_max = np.max(plot_input)
        norm = TwoSlopeNorm(vmin=lim_min,vcenter=0,vmax=lim_max)
        ticks_negative = np.linspace(0.99*lim_min,0,5)
        ticks_positive = np.linspace(0,1.01*lim_max,5)
        ticks = np.append(ticks_negative[:-1],ticks_positive)
        
        return norm,ticks
   
    def plot_cross_2d(self,form="polar",energy_limits=[0.3,10.5]):
        """   
        Plots the a two-dimensional cross spectrum as a function of Fourier 
        frequency and energy.
        
        Parameters
        ----------
        form: string 
            A qualifier to choose in which units to plot the cross spectrum. 
            By default, form="polar" will plot the modulus, phase, and lag 
            spectrum. Alternatively, form="cartesian" plots the real 
            and imaginary parts of the cross spectrum.
            
        energy_limits: list 
            The lower and upper bound to be used in the energy axis of the 
            cross spectrum.
        """
        energy_indexes = np.where(np.logical_and(self.energ>energy_limits[0],
                                                 self.energ<energy_limits[1]))
        
        if form == "cartesian":
            norm_real, ticks_real = self._plot_limits(
                                    self.real()[energy_indexes,:])
            norm_imag, ticks_imag = self._plot_limits(
                                    self.imag()[energy_indexes,:])
            
            fig, ((ax1,ax2)) = plt.subplots(1,2,figsize=(12.5,5.))
            
            real = ax1.pcolormesh(self.freqs,self.energ,self.real(),cmap="PuOr",
                                  shading='auto',linewidth=0,
                                  rasterized=True,norm=norm_real)
            cb = fig.colorbar(real,ax=ax1,ticks=ticks_real,format="%.1f")
            ax1.set_xscale("log",base=10)
            ax1.set_title("Real")
            ax1.set_xlabel("Frequency")
            ax1.set_ylabel("Energy")
            ax1.set_ylim([energy_limits[0],energy_limits[1]])
            
            imag = ax2.pcolormesh(self.freqs,self.energ,self.imag(),cmap="PuOr",
                                  shading='auto',linewidth=0,
                                  rasterized=True,norm=norm_imag)
            cb = fig.colorbar(imag,ax=ax2,ticks=ticks_imag,format="%.1f")              
            ax2.set_xscale("log",base=10)
            ax2.set_title("Imaginary")
            ax2.set_xlabel("Frequency")
            ax2.set_ylabel("Energy")
            ax2.set_ylim([energy_limits[0],energy_limits[1]])
            
            plt.tight_layout()
            plt.show()
        elif form == "polar":
            norm_phase, ticks_phase = self._plot_limits(
                                      self.phase()[energy_indexes,:])            
            norm_lag, ticks_lag = self._plot_limits(
                                  self.lag()[energy_indexes,:])
            
            fig, ((ax1,ax2,ax3)) = plt.subplots(1,3,figsize=(15.,5.))
            modulus = ax1.pcolormesh(self.freqs,self.energ,self.mod(),
                                     cmap="magma_r",shading='auto',
                                     linewidth=0,rasterized=True)
            cb = fig.colorbar(modulus,ax=ax1,format="%.1f")            
            ax1.set_xscale("log",base=10)
            ax1.set_title("Modulus")
            ax1.set_xlabel("Frequency")
            ax1.set_ylabel("Energy")
            ax1.set_ylim([energy_limits[0],energy_limits[1]])
           
            phase = ax2.pcolormesh(self.freqs,self.energ,self.phase(),cmap="PuOr",
                                   shading='auto',linewidth=0,
                                   rasterized=True,norm=norm_phase)
            cb = fig.colorbar(phase,ax=ax2,ticks=ticks_phase,format="%.2f")           
            ax2.set_xscale("log",base=10)
            ax2.set_title("Phase")
            ax2.set_xlabel("Frequency")
            ax2.set_ylabel("Energy")
            ax2.set_ylim([energy_limits[0],energy_limits[1]])
            
            lags = ax3.pcolormesh(self.freqs,self.energ,self.lag(),cmap="PuOr",
                                  shading='auto',linewidth=0,
                                  rasterized=True,norm=norm_lag)
            cb = fig.colorbar(lags,ax=ax3,ticks=ticks_lag,format="%.2f")
            ax3.set_xscale("log",base=10)
            ax3.set_title("Lag")
            ax3.set_xlabel("Frequency")
            ax3.set_ylabel("Energy")
            ax3.set_ylim([energy_limits[0],energy_limits[1]])            
            
            plt.tight_layout()
            plt.show()
        else:
            raise ValueError("plot mode not supported")
        return        